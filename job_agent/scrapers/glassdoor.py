"""Glassdoor scraper. Browses the public job search results."""
from __future__ import annotations

import logging
import urllib.parse

from .base import BaseScraper, JobPosting, human_pause

log = logging.getLogger(__name__)


class GlassdoorScraper(BaseScraper):
    platform = "glassdoor"
    storage_state_name = "glassdoor"

    BASE = "https://www.glassdoor.com/Job/jobs.htm"

    async def search(self, page, role: str, location: str, remaining: int) -> list[JobPosting]:
        params = {"sc.keyword": role, "locT": "C", "locKeyword": location, "fromAge": "7"}
        url = self.BASE + "?" + urllib.parse.urlencode(params)
        await page.goto(url, wait_until="domcontentloaded")
        await human_pause()

        try:
            close = await page.query_selector("button[aria-label='Close']")
            if close:
                await close.click()
        except Exception:  # noqa: BLE001
            pass

        cards = await page.query_selector_all("li.react-job-listing, div[data-test='jobListing']")
        postings: list[JobPosting] = []
        for card in cards[:remaining]:
            try:
                title_el = await card.query_selector("a[data-test='job-link'], a.jobLink")
                company_el = await card.query_selector("[data-test='employer-name'], div.d-flex span")
                loc_el = await card.query_selector("[data-test='emp-location'], span.loc")
                if not title_el:
                    continue
                href = await title_el.get_attribute("href")
                title = (await title_el.inner_text()).strip()
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                loc = (await loc_el.inner_text()).strip() if loc_el else location
                if href and href.startswith("/"):
                    href = "https://www.glassdoor.com" + href
                if not href:
                    continue

                description = await self._fetch_description(page, href)
                postings.append(
                    JobPosting(
                        title=title,
                        company=company,
                        location=loc,
                        url=href.split("?")[0],
                        platform=self.platform,
                        description=description,
                        work_type="remote" if "remote" in loc.lower() else None,
                    )
                )
            except Exception as e:  # noqa: BLE001
                log.debug("Glassdoor card skip: %s", e)
        return postings

    async def _fetch_description(self, page, href: str) -> str:
        try:
            ctx = page.context
            tab = await ctx.new_page()
            await tab.goto(href, wait_until="domcontentloaded")
            await human_pause(short=True)
            el = await tab.query_selector(".jobDescriptionContent, div[class*='JobDescription']")
            text = (await el.inner_text()).strip() if el else ""
            await tab.close()
            return text[:8000]
        except Exception as e:  # noqa: BLE001
            log.debug("Glassdoor description fetch failed: %s", e)
            return ""
