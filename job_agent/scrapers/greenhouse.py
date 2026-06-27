"""Greenhouse public boards scraper.

Many top tech companies publish their open roles at
https://boards-api.greenhouse.io/v1/boards/{slug}/jobs as free JSON.
No auth needed. We just walk a curated list of companies that hire
data / ML / analytics roles in the US.
"""
from __future__ import annotations

import asyncio
import logging
import re

import requests

from .base import BaseScraper, JobPosting

log = logging.getLogger(__name__)


# Slugs from boards.greenhouse.io/<slug>. Add/remove freely.
GREENHOUSE_COMPANIES = [
    "stripe",
    "airbnb",
    "datadog",
    "doordash",
    "plaid",
    "snowflake",
    "scaleai",
    "twilio",
    "robinhood",
    "instacart",
    "coinbase",
    "discord",
    "asana",
    "figma",
    "anthropic",
    "openai",
    "perplexityai",
    "ramp",
    "brex",
    "samsara",
    "carta",
    "elastic",
    "cloudflare",
    "mongodb",
    "atlassian",
    "anduril",
]


class GreenhouseScraper(BaseScraper):
    platform = "greenhouse"
    storage_state_name = None

    BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

    async def run(self, roles: list[str], locations: list[str], max_jobs: int) -> list[dict]:
        loop = asyncio.get_event_loop()
        role_terms = [r.lower() for r in roles]

        def fetch(slug: str) -> list[dict]:
            try:
                url = self.BASE.format(slug=slug)
                r = requests.get(url, params={"content": "true"}, timeout=15)
                if r.status_code == 404:
                    return []
                r.raise_for_status()
                return r.json().get("jobs", [])
            except Exception as e:  # noqa: BLE001
                log.debug("Greenhouse %s failed: %s", slug, e)
                return []

        results: list[dict] = []
        for slug in GREENHOUSE_COMPANIES:
            if len(results) >= max_jobs:
                break
            jobs = await loop.run_in_executor(None, fetch, slug)
            if not jobs:
                continue
            matched = 0
            for j in jobs:
                if len(results) >= max_jobs:
                    break
                title = (j.get("title") or "").strip()
                if not any(t in title.lower() for t in role_terms):
                    continue
                url = j.get("absolute_url", "")
                if not url:
                    continue
                location = (j.get("location") or {}).get("name", "Unknown")
                description = self._clean_html(j.get("content", ""))
                company = slug.replace("-", " ").title()
                results.append(
                    JobPosting(
                        title=title,
                        company=company,
                        location=location,
                        url=url,
                        platform=self.platform,
                        description=description[:8000],
                        work_type="remote" if "remote" in location.lower() else None,
                    ).to_dict()
                )
                matched += 1
            log.info("[greenhouse] %s: %d/%d matched", slug, matched, len(jobs))
        log.info("[greenhouse] total: %d jobs", len(results))
        return results

    @staticmethod
    def _clean_html(html: str) -> str:
        import html as html_lib

        text = html_lib.unescape(html or "")
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
