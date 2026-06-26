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
    FLASK_HOST,
    FLASK_PORT,
    LOG_FILE,
    LOCATIONS,
    MAX_JOBS_PER_RUN,
    MIN_FIT_SCORE,
    SCHEDULE_HOURS,
    TARGET_ROLES,
)
from db import init_db, insert_job, url_exists
from scorer import score_job
from scrapers import GlassdoorScraper, IndeedScraper, LinkedInScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("agent")


def _dedupe(jobs: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for j in jobs:
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
    return out


async def _scrape_all() -> list[dict]:
    per_platform = max(1, MAX_JOBS_PER_RUN // 3)
    scrapers = [
        LinkedInScraper(headless=False),
        IndeedScraper(headless=False),
        GlassdoorScraper(headless=True),
    ]
    tasks = [s.run(TARGET_ROLES, LOCATIONS, per_platform) for s in scrapers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[dict] = []
    for s, r in zip(scrapers, results):
        if isinstance(r, Exception):
            log.error("%s scrape error: %s", s.platform, r)
            continue
        log.info("%s returned %d jobs", s.platform, len(r))
        out.extend(r)
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
    log.info("Pipeline start at %s", datetime.utcnow().isoformat())

    raw = asyncio.run(_scrape_all())
    log.info("Scraped %d total raw jobs", len(raw))

    deduped = _dedupe(raw)
    log.info("After dedupe / url check: %d jobs", len(deduped))
    deduped = deduped[:MAX_JOBS_PER_RUN]

    scored = _score_parallel(deduped)

    stored = 0
    for j in scored:
        if j["fit_score"] >= MIN_FIT_SCORE:
            j["status"] = "pending"
            if insert_job(j):
                stored += 1

    elapsed = time.time() - start
    summary = {
        "scraped": len(raw),
        "deduped": len(deduped),
        "stored": stored,
        "elapsed_seconds": round(elapsed, 1),
    }
    log.info("Pipeline done %s", summary)
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
