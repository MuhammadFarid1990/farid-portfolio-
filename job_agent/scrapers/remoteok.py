"""Remote OK API scraper. Free, no auth, returns JSON of remote jobs."""
from __future__ import annotations

import asyncio
import logging
import re

import requests

from .base import BaseScraper, JobPosting

log = logging.getLogger(__name__)


class RemoteOKScraper(BaseScraper):
    platform = "remoteok"
    storage_state_name = None

    ENDPOINT = "https://remoteok.com/api"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 JobAgent/1.0",
        "Accept": "application/json",
    }

    async def run(self, roles: list[str], locations: list[str], max_jobs: int) -> list[dict]:
        loop = asyncio.get_event_loop()
        log.info("[remoteok] fetching feed")

        def fetch() -> list[dict]:
            try:
                r = requests.get(self.ENDPOINT, headers=self.HEADERS, timeout=20)
                r.raise_for_status()
                data = r.json()
                return [j for j in data if isinstance(j, dict) and j.get("position")]
            except Exception as e:  # noqa: BLE001
                log.warning("Remote OK fetch failed: %s", e)
                return []

        feed = await loop.run_in_executor(None, fetch)
        log.info("[remoteok] %d jobs in feed", len(feed))

        role_terms = [r.lower() for r in roles]
        results: list[dict] = []
        for j in feed:
            if len(results) >= max_jobs:
                break
            title = (j.get("position") or "").strip()
            if not any(t in title.lower() for t in role_terms):
                continue
            url = j.get("url") or j.get("apply_url") or ""
            if not url:
                continue
            description = self._clean_html(j.get("description", ""))
            results.append(
                JobPosting(
                    title=title,
                    company=j.get("company", "Unknown"),
                    location=j.get("location") or "Remote",
                    url=url,
                    platform=self.platform,
                    description=description[:8000],
                    work_type="remote",
                ).to_dict()
            )
        log.info("[remoteok] %d matched role keywords", len(results))
        return results

    @staticmethod
    def _clean_html(html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html or "")
        text = re.sub(r"\s+", " ", text)
        return text.strip()
