"""Remotive API scraper. Free, no auth, returns clean JSON of remote tech jobs.

Endpoint: https://remotive.com/api/remote-jobs
We don't even need Playwright for this one — it's a plain HTTP call.
"""
from __future__ import annotations

import asyncio
import logging
import re

import requests

from .base import BaseScraper, JobPosting

log = logging.getLogger(__name__)


class RemotiveScraper(BaseScraper):
    platform = "remotive"
    storage_state_name = None

    ENDPOINT = "https://remotive.com/api/remote-jobs"

    async def run(self, roles: list[str], locations: list[str], max_jobs: int) -> list[dict]:
        # Locations are irrelevant — every Remotive job is remote.
        # We hit the API once per role and merge results.
        results: list[dict] = []
        seen: set[str] = set()

        def fetch(role: str) -> list[dict]:
            try:
                r = requests.get(self.ENDPOINT, params={"search": role}, timeout=15)
                r.raise_for_status()
                return r.json().get("jobs", [])
            except Exception as e:  # noqa: BLE001
                log.warning("Remotive fetch failed for '%s': %s", role, e)
                return []

        loop = asyncio.get_event_loop()
        for role in roles:
            if len(results) >= max_jobs:
                break
            log.info("[remotive] fetching '%s'", role)
            jobs = await loop.run_in_executor(None, fetch, role)
            for j in jobs:
                if len(results) >= max_jobs:
                    break
                url = j.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                description = self._clean_html(j.get("description", ""))
                results.append(
                    JobPosting(
                        title=j.get("title", role),
                        company=j.get("company_name", "Unknown"),
                        location=j.get("candidate_required_location", "Remote"),
                        url=url,
                        platform=self.platform,
                        description=description[:8000],
                        work_type="remote",
                    ).to_dict()
                )
        log.info("[remotive] returning %d jobs", len(results))
        return results

    @staticmethod
    def _clean_html(html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
