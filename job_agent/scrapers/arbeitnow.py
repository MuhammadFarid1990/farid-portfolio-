"""Arbeitnow API scraper. Free, no auth, JSON of remote and onsite jobs."""
from __future__ import annotations

import asyncio
import logging
import re

import requests

from .base import BaseScraper, JobPosting

log = logging.getLogger(__name__)


class ArbeitnowScraper(BaseScraper):
    platform = "arbeitnow"
    storage_state_name = None

    ENDPOINT = "https://arbeitnow.com/api/job-board-api"

    async def run(self, roles: list[str], locations: list[str], max_jobs: int) -> list[dict]:
        loop = asyncio.get_event_loop()
        log.info("[arbeitnow] fetching feed")

        def fetch(page: int) -> list[dict]:
            try:
                r = requests.get(self.ENDPOINT, params={"page": page}, timeout=20)
                r.raise_for_status()
                return r.json().get("data", [])
            except Exception as e:  # noqa: BLE001
                log.warning("Arbeitnow fetch page %d failed: %s", page, e)
                return []

        feed: list[dict] = []
        for page in range(1, 4):  # up to 3 pages
            page_data = await loop.run_in_executor(None, fetch, page)
            if not page_data:
                break
            feed.extend(page_data)
        log.info("[arbeitnow] %d total jobs in feed", len(feed))

        role_terms = [r.lower() for r in roles]
        results: list[dict] = []
        for j in feed:
            if len(results) >= max_jobs:
                break
            title = (j.get("title") or "").strip()
            if not any(t in title.lower() for t in role_terms):
                continue
            url = j.get("url", "")
            if not url:
                continue
            description = self._clean_html(j.get("description", ""))
            location = j.get("location") or "Remote"
            is_remote = bool(j.get("remote"))
            results.append(
                JobPosting(
                    title=title,
                    company=j.get("company_name", "Unknown"),
                    location=location,
                    url=url,
                    platform=self.platform,
                    description=description[:8000],
                    work_type="remote" if is_remote else None,
                ).to_dict()
            )
        log.info("[arbeitnow] %d matched role keywords", len(results))
        return results

    @staticmethod
    def _clean_html(html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html or "")
        text = re.sub(r"\s+", " ", text)
        return text.strip()
