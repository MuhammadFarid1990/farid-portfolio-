"""The Muse API scraper. Free public API, no auth required."""
from __future__ import annotations

import asyncio
import logging
import re

import requests

from .base import BaseScraper, JobPosting

log = logging.getLogger(__name__)


class TheMuseScraper(BaseScraper):
    platform = "themuse"
    storage_state_name = None

    ENDPOINT = "https://www.themuse.com/api/public/jobs"
    CATEGORIES = ["Data Science", "Software Engineer", "Data and Analytics"]

    async def run(self, roles: list[str], locations: list[str], max_jobs: int) -> list[dict]:
        loop = asyncio.get_event_loop()

        def fetch(page: int, category: str) -> list[dict]:
            try:
                params = {"page": page, "category": category, "location": "Flexible / Remote"}
                r = requests.get(self.ENDPOINT, params=params, timeout=20)
                r.raise_for_status()
                return r.json().get("results", [])
            except Exception as e:  # noqa: BLE001
                log.warning("Muse fetch %s page %d failed: %s", category, page, e)
                return []

        seen: set[str] = set()
        results: list[dict] = []
        for category in self.CATEGORIES:
            if len(results) >= max_jobs:
                break
            log.info("[themuse] category=%s", category)
            for page in range(0, 3):
                if len(results) >= max_jobs:
                    break
                page_data = await loop.run_in_executor(None, fetch, page, category)
                if not page_data:
                    break
                for j in page_data:
                    if len(results) >= max_jobs:
                        break
                    title = (j.get("name") or "").strip()
                    locs = j.get("locations") or []
                    location = locs[0].get("name") if locs else "Remote"
                    refs = j.get("refs") or {}
                    url = refs.get("landing_page", "")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    company = (j.get("company") or {}).get("name", "Unknown")
                    description = self._clean_html(j.get("contents", ""))
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
        log.info("[themuse] returning %d jobs", len(results))
        return results

    @staticmethod
    def _clean_html(html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html or "")
        text = re.sub(r"\s+", " ", text)
        return text.strip()
