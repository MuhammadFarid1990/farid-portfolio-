"""Orchestrator. Runs scrape -> dedupe -> score -> store -> open dashboard.

Also schedules the pipeline at the times set in config.SCHEDULE_HOURS and
serves the Flask dashboard in the main thread.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from config import (
    AUTO_APPLY,
    ENABLED_PLATFORMS,
    FLASK_HOST,
    FLASK_PORT,
    LOG_FILE,
    LOCATIONS,
    MAX_JOBS_PER_RUN,
    MIN_FIT_SCORE,
    SCHEDULE_HOURS,
    SCRAPER_TIMEOUT,
    TARGET_ROLES,
)
from db import init_db, insert_job, url_exists
from scorer import score_job
from scrapers import (
    ArbeitnowScraper,
    GlassdoorScraper,
    GreenhouseScraper,
    IndeedScraper,
    LinkedInScraper,
    RemoteOKScraper,
    RemotiveScraper,
    TheMuseScraper,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("agent")


NON_US_KEYWORDS = {
    # countries / regions / common non-US city names
    "canada", "toronto", "vancouver", "ontario", "montreal", "ottawa",
    "uk", "united kingdom", "england", "scotland", "london", "manchester", "edinburgh", "bristol",
    "ireland", "dublin", "cork",
    "germany", "berlin", "munich", "hamburg", "deutschland",
    "france", "paris", "lyon",
    "netherlands", "amsterdam", "rotterdam",
    "spain", "madrid", "barcelona",
    "italy", "rome", "milan",
    "poland", "warsaw", "krakow",
    "portugal", "lisbon",
    "sweden", "stockholm",
    "denmark", "copenhagen",
    "norway", "oslo",
    "switzerland", "zurich", "geneva",
    "australia", "sydney", "melbourne",
    "new zealand", "auckland",
    "india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune", "chennai", "noida", "gurgaon",
    "pakistan", "karachi", "lahore", "islamabad",
    "japan", "tokyo", "osaka",
    "korea", "seoul",
    "china", "shanghai", "beijing", "shenzhen",
    "singapore",
    "philippines", "manila",
    "malaysia", "kuala lumpur",
    "indonesia", "jakarta",
    "vietnam", "hanoi", "ho chi minh",
    "thailand", "bangkok",
    "mexico", "mexico city",
    "brazil", "sao paulo", "rio de janeiro",
    "argentina", "buenos aires",
    "colombia", "bogota",
    "chile", "santiago",
    "uae", "dubai", "abu dhabi",
    "saudi", "riyadh",
    "israel", "tel aviv",
    "south africa", "cape town", "johannesburg",
    "nigeria", "lagos",
    "kenya", "nairobi",
    "egypt", "cairo",
    "emea", "apac", "latam", "eu only", "europe only",
}


def _is_non_us_location(location: str) -> bool:
    loc = (location or "").lower()
    if not loc:
        return False
    if "remote" in loc and any(s in loc for s in ("us", "u.s.", "usa", "united states", "north america", "americas", "anywhere")):
        return False
    return any(k in loc for k in NON_US_KEYWORDS)


def _dedupe(jobs: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    dropped_non_us = 0
    for j in jobs:
        if _is_non_us_location(j.get("location", "")):
            dropped_non_us += 1
            continue
        key = (
            (j.get("company") or "").strip().lower(),
            (j.get("title") or "").strip().lower(),
            (j.get("location") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        if url_exists(j.get("url", "")):
            continue
        out.append(j)
    if dropped_non_us:
        log.info("Dropped %d non-US jobs before scoring", dropped_non_us)
    return out


async def _scrape_all() -> list[dict]:
    available = {
        "linkedin": LinkedInScraper(headless=False),
        "indeed": IndeedScraper(headless=False),
        "glassdoor": GlassdoorScraper(headless=True),
        "remotive": RemotiveScraper(),
        "remoteok": RemoteOKScraper(),
        "arbeitnow": ArbeitnowScraper(),
        "themuse": TheMuseScraper(),
        "greenhouse": GreenhouseScraper(),
    }
    scrapers = [available[p] for p in ENABLED_PLATFORMS if p in available]
    if not scrapers:
        log.warning("No enabled scrapers; check ENABLED_PLATFORMS in config")
        return []
    per_platform = max(1, MAX_JOBS_PER_RUN // len(scrapers))
    log.info("Scraping %s, ~%d jobs each, %ds timeout", [s.platform for s in scrapers], per_platform, SCRAPER_TIMEOUT)

    async def _bounded(s):
        try:
            return await asyncio.wait_for(
                s.run(TARGET_ROLES, LOCATIONS, per_platform),
                timeout=SCRAPER_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log.error("%s timed out after %ds — moving on", s.platform, SCRAPER_TIMEOUT)
            return []
        except Exception as e:  # noqa: BLE001
            log.error("%s crashed: %s", s.platform, e)
            return []

    results = await asyncio.gather(*[_bounded(s) for s in scrapers])
    out: list[dict] = []
    for s, r in zip(scrapers, results):
        log.info("[%s] returned %d jobs", s.platform, len(r))
        out.extend(r)
    log.info("Scrape phase done: %d jobs across all platforms", len(out))
    return out


def _score_parallel(jobs: list[dict]) -> list[dict]:
    """Score jobs in parallel threads. Claude API is rate-limited so cap at 5."""
    scored: list[dict] = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(score_job, j): j for j in jobs}
        for fut in as_completed(futures):
            j = futures[fut]
            try:
                result = fut.result()
            except Exception as e:  # noqa: BLE001
                log.exception("score future failed")
                result = {"score": 0, "reason": str(e), "cover_letter": ""}
            j["fit_score"] = result["score"]
            j["fit_reason"] = result["reason"]
            j["cover_letter"] = result["cover_letter"]
            scored.append(j)
            log.info(
                "Scored %s @ %s -> %d", j.get("title"), j.get("company"), result["score"]
            )
    return scored


def run_pipeline_once() -> dict:
    init_db()
    start = time.time()
    log.info("=" * 60)
    log.info("PIPELINE START at %s", datetime.utcnow().isoformat())
    log.info("Roles: %d | Locations: %d | Platforms: %s", len(TARGET_ROLES), len(LOCATIONS), ENABLED_PLATFORMS)
    log.info("=" * 60)

    raw = asyncio.run(_scrape_all())
    log.info("PHASE 1 done: %d raw jobs", len(raw))

    deduped = _dedupe(raw)
    log.info("PHASE 2 done: %d after dedupe", len(deduped))
    deduped = deduped[:MAX_JOBS_PER_RUN]

    log.info("PHASE 3 starting: scoring %d jobs with Claude", len(deduped))
    scored = _score_parallel(deduped)

    stored_ids: list[int] = []
    for j in scored:
        if j["fit_score"] >= MIN_FIT_SCORE:
            j["status"] = "pending"
            row_id = insert_job(j)
            if row_id:
                stored_ids.append(row_id)

    elapsed = time.time() - start
    summary = {
        "scraped": len(raw),
        "deduped": len(deduped),
        "stored": len(stored_ids),
        "elapsed_seconds": round(elapsed, 1),
    }
    log.info("Pipeline done %s", summary)

    if AUTO_APPLY and stored_ids:
        log.info("AUTO_APPLY on -> submitting %d jobs", len(stored_ids))
        try:
            from applicator import run_apply_many

            run_apply_many(stored_ids)
        except Exception:  # noqa: BLE001
            log.exception("auto-apply failed")

    return summary


def _open_browser_when_ready() -> None:
    import socket

    for _ in range(40):
        try:
            with socket.create_connection((FLASK_HOST, FLASK_PORT), timeout=0.5):
                break
        except OSError:
            time.sleep(0.25)
    webbrowser.open(f"http://{FLASK_HOST}:{FLASK_PORT}")


def main() -> None:
    init_db()
    scheduler = BackgroundScheduler()
    for hour in SCHEDULE_HOURS:
        scheduler.add_job(run_pipeline_once, "cron", hour=hour, minute=0, id=f"run_{hour}")
    scheduler.start()
    log.info("Scheduler armed for hours: %s", SCHEDULE_HOURS)

    threading.Thread(target=_open_browser_when_ready, daemon=True).start()

    from app import serve

    try:
        serve()
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
