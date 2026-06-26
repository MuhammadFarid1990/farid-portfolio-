"""Indeed scraper. Public search, no login required for browsing."""
from __future__ import annotations

import logging
import urllib.parse

from .base import BaseScraper, JobPosting, human_pause

log = logging.getLogger(__name__)


class IndeedScraper(BaseScraper):
    platform = "indeed"
    storage_state_name = "indeed"

    BASE = "https://www.indeed.com/jobs"

    async def search(self, page, role: str, location: str, remaining: int) -> list[JobPosting]:
        params = {"q": role, "l": location, "fromage": "7"}
        if location.lower() == "remote":
            params["sc"] = "0kf:attr(DSQF7);"
        url = self.BASE + "?" + urllib.parse.urlencode(params)
        await page.goto(url, wait_until="domcontentloaded")
        await human_pause()

        cards = await page.query_selector_all("a.tapItem, div.job_seen_beacon")
        postings: list[JobPosting] = []
        for card in cards[:remaining]:
            try:
                title_el = await card.query_selector("h2 a span, h2.jobTitle span")
                company_el = await card.query_selector(
                    "span.companyName, [data-testid='company-name']"
                )
                loc_el = await card.query_selector(
                    ".companyLocation, [data-testid='text-location']"
                )
                link_el = await card.query_selector("h2 a, a.tapItem")
                if not link_el:
                    continue
                href = await link_el.get_attribute("href")
                if not href:
                    continue
                if href.startswith("/"):
                    href = "https://www.indeed.com" + href
                title = (await title_el.inner_text()).strip() if title_el else role
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                loc = (await loc_el.inner_text()).strip() if loc_el else location

                description = await self._fetch_description(page, href)
                postings.append(
                    JobPosting(
                        title=title,
                        company=company,
                        location=loc,
                        url=href.split("&")[0],
                        platform=self.platform,
                        description=description,
                        work_type="remote" if "remote" in loc.lower() else None,
                    )
                )
            except Exception as e:  # noqa: BLE001
                log.debug("Indeed card skip: %s", e)
        return postings

    async def _fetch_description(self, page, href: str) -> str:
        try:
            ctx = page.context
            tab = await ctx.new_page()
            await tab.goto(href, wait_until="domcontentloaded")
            await human_pause(short=True)
            el = await tab.query_selector("#jobDescriptionText")
            text = (await el.inner_text()).strip() if el else ""
            await tab.close()
            return text[:8000]
        except Exception as e:  # noqa: BLE001
            log.debug("Indeed description fetch failed: %s", e)
            return ""
