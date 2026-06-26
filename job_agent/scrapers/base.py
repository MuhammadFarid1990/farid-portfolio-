"""Base scraper. Subclasses implement `search` and return JobPosting dicts."""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import asdict, dataclass, field
from typing import Optional

from playwright.async_api import BrowserContext, async_playwright

from config import HUMAN_DELAY_MAX, HUMAN_DELAY_MIN, SESSION_DIR

log = logging.getLogger(__name__)


@dataclass
class JobPosting:
    title: str
    company: str
    location: str
    url: str
    platform: str
    description: str = ""
    work_type: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("extra", None)
        return d


async def human_pause(short: bool = False) -> None:
    """Random jitter to look less like a bot."""
    lo, hi = (0.5, 1.5) if short else (HUMAN_DELAY_MIN, HUMAN_DELAY_MAX)
    await asyncio.sleep(random.uniform(lo, hi))


class BaseScraper:
    """Override `platform`, `login`, and `search`."""

    platform: str = "base"
    storage_state_name: Optional[str] = None

    def __init__(self, headless: bool = False) -> None:
        self.headless = headless

    @property
    def storage_path(self) -> Optional[str]:
        if not self.storage_state_name:
            return None
        return str(SESSION_DIR / f"{self.storage_state_name}.json")

    async def _new_context(self, p) -> tuple:
        browser = await p.chromium.launch(headless=self.headless)
        storage = self.storage_path
        ctx_kwargs: dict = {
            "viewport": {"width": 1366, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        if storage:
            import os

            if os.path.exists(storage):
                ctx_kwargs["storage_state"] = storage
        context = await browser.new_context(**ctx_kwargs)
        return browser, context

    async def _save_storage(self, context: BrowserContext) -> None:
        if self.storage_path:
            await context.storage_state(path=self.storage_path)

    async def run(self, roles: list[str], locations: list[str], max_jobs: int) -> list[dict]:
        """Public entrypoint. Returns list[dict] of jobs."""
        results: list[dict] = []
        async with async_playwright() as p:
            browser, context = await self._new_context(p)
            page = await context.new_page()
            try:
                await self.login(page)
                await self._save_storage(context)
                for role in roles:
                    for location in locations:
                        if len(results) >= max_jobs:
                            break
                        try:
                            postings = await self.search(page, role, location, max_jobs - len(results))
                            results.extend(p.to_dict() for p in postings)
                        except Exception as e:  # noqa: BLE001
                            log.warning("%s search failed for %s/%s: %s", self.platform, role, location, e)
                        await human_pause()
                    if len(results) >= max_jobs:
                        break
            finally:
                await context.close()
                await browser.close()
        return results

    async def login(self, page) -> None:  # noqa: D401
        """Optional. Override when the platform needs auth."""
        return

    async def search(self, page, role: str, location: str, remaining: int) -> list[JobPosting]:
        raise NotImplementedError
