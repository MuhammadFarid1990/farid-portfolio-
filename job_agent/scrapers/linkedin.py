"""LinkedIn scraper. Logs in once, caches session cookies."""
from __future__ import annotations

import logging
import urllib.parse

from config import LINKEDIN_EMAIL, LINKEDIN_PASSWORD

from .base import BaseScraper, JobPosting, human_pause

log = logging.getLogger(__name__)


class LinkedInScraper(BaseScraper):
    platform = "linkedin"
    storage_state_name = "linkedin"

    LOGIN_URL = "https://www.linkedin.com/login"
    JOBS_URL = "https://www.linkedin.com/jobs/search/"

    async def login(self, page) -> None:
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        if "/feed" in page.url:
            log.info("LinkedIn session reused")
            return
        if not (LINKEDIN_EMAIL and LINKEDIN_PASSWORD):
            log.warning("LinkedIn creds missing; continuing unauthenticated")
            return
        await page.goto(self.LOGIN_URL, wait_until="domcontentloaded")
        await page.fill("input#username", LINKEDIN_EMAIL)
        await page.fill("input#password", LINKEDIN_PASSWORD)
        await human_pause(short=True)
        await page.click("button[type=submit]")
        try:
            await page.wait_for_url("**/feed/**", timeout=20000)
            log.info("LinkedIn login ok")
        except Exception:  # noqa: BLE001
            log.warning("LinkedIn login may have hit a challenge")

    async def search(self, page, role: str, location: str, remaining: int) -> list[JobPosting]:
        params = {
            "keywords": role,
            "location": location,
            "f_WT": "2,3" if location.lower() == "remote" else "",
            "f_TPR": "r604800",  # past week
        }
        url = self.JOBS_URL + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v})
        await page.goto(url, wait_until="domcontentloaded")
        await human_pause()

        cards = await page.query_selector_all("ul.jobs-search__results-list li, div.job-card-container")
        postings: list[JobPosting] = []
        for card in cards[:remaining]:
            try:
                link = await card.query_selector("a")
                if not link:
                    continue
                href = await link.get_attribute("href")
                if not href:
                    continue
                title_el = await card.query_selector(
                    "h3, .base-search-card__title, .job-card-list__title"
                )
                company_el = await card.query_selector(
                    "h4, .base-search-card__subtitle, .job-card-container__company-name"
                )
                location_el = await card.query_selector(
                    ".job-search-card__location, .job-card-container__metadata-item"
                )
                title = (await title_el.inner_text()).strip() if title_el else role
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                loc = (await location_el.inner_text()).strip() if location_el else location

                description = await self._fetch_description(page, href)
                postings.append(
                    JobPosting(
                        title=title,
                        company=company,
                        location=loc,
                        url=href.split("?")[0],
                        platform=self.platform,
                        description=description,
                        work_type=("remote" if "remote" in loc.lower() else None),
                    )
                )
            except Exception as e:  # noqa: BLE001
                log.debug("LinkedIn card skip: %s", e)
        return postings

    async def _fetch_description(self, page, href: str) -> str:
        try:
            ctx = page.context
            tab = await ctx.new_page()
            await tab.goto(href, wait_until="domcontentloaded")
            await human_pause(short=True)
            sel = (
                ".show-more-less-html__markup, "
                ".jobs-description-content__text, "
                "div.description__text"
            )
            el = await tab.query_selector(sel)
            text = (await el.inner_text()).strip() if el else ""
            await tab.close()
            return text[:8000]
        except Exception as e:  # noqa: BLE001
            log.debug("LinkedIn description fetch failed: %s", e)
            return ""
