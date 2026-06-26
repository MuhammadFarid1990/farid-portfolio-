"""Playwright auto-apply. Handles LinkedIn Easy Apply, Indeed Apply, external sites."""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from datetime import datetime

from playwright.async_api import Page, async_playwright

from config import (
    APPLY_DELAY_SECONDS,
    CANDIDATE_EMAIL,
    CANDIDATE_LINKEDIN,
    CANDIDATE_NAME,
    CANDIDATE_PHONE,
    CANDIDATE_WEBSITE,
    HUMAN_DELAY_MAX,
    HUMAN_DELAY_MIN,
    LINKEDIN_EMAIL,
    LINKEDIN_PASSWORD,
    REQUIRES_SPONSORSHIP,
    RESUME_PDF,
    SALARY_EXPECTATION,
    SCREENSHOT_DIR,
    SESSION_DIR,
    WORK_AUTHORIZED_US,
)
from db import update_status

log = logging.getLogger(__name__)


async def _human_pause(short: bool = False) -> None:
    lo, hi = (0.5, 1.5) if short else (HUMAN_DELAY_MIN, HUMAN_DELAY_MAX)
    await asyncio.sleep(random.uniform(lo, hi))


FIELD_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"first.?name", re.I), CANDIDATE_NAME.split()[0]),
    (re.compile(r"last.?name", re.I), CANDIDATE_NAME.split()[-1]),
    (re.compile(r"full.?name|^name", re.I), CANDIDATE_NAME),
    (re.compile(r"email", re.I), CANDIDATE_EMAIL),
    (re.compile(r"phone|mobile|cell", re.I), CANDIDATE_PHONE),
    (re.compile(r"linkedin", re.I), CANDIDATE_LINKEDIN),
    (re.compile(r"website|portfolio|personal site", re.I), CANDIDATE_WEBSITE),
    (re.compile(r"salary|compensation", re.I), SALARY_EXPECTATION),
]


YES_NO_FIELDS: list[tuple[re.Pattern, bool]] = [
    (re.compile(r"authoriz", re.I), WORK_AUTHORIZED_US),
    (re.compile(r"legally.*work|us.?citizen|permanent.?resident", re.I), WORK_AUTHORIZED_US),
    (re.compile(r"sponsor", re.I), REQUIRES_SPONSORSHIP),
    (re.compile(r"visa", re.I), REQUIRES_SPONSORSHIP),
]


def _label_match(label: str) -> str | None:
    for pat, value in FIELD_MAP:
        if pat.search(label):
            return value
    return None


def _yes_no_match(label: str) -> bool | None:
    for pat, value in YES_NO_FIELDS:
        if pat.search(label):
            return value
    return None


async def _fill_form_fields(page: Page) -> None:
    """Best-effort: walk every input and select on the page, fill what we recognize."""
    inputs = await page.query_selector_all("input, textarea")
    for el in inputs:
        try:
            input_type = (await el.get_attribute("type") or "").lower()
            if input_type in ("hidden", "submit", "button", "file", "checkbox", "radio"):
                continue
            label = (
                await el.get_attribute("aria-label")
                or await el.get_attribute("name")
                or await el.get_attribute("placeholder")
                or await el.get_attribute("id")
                or ""
            )
            value = _label_match(label)
            if value:
                current = await el.input_value()
                if not current:
                    await el.fill(value)
                    await _human_pause(short=True)
        except Exception as e:  # noqa: BLE001
            log.debug("input skip: %s", e)

    selects = await page.query_selector_all("select")
    for sel in selects:
        try:
            label = (
                await sel.get_attribute("aria-label")
                or await sel.get_attribute("name")
                or await sel.get_attribute("id")
                or ""
            )
            yn = _yes_no_match(label)
            if yn is None:
                continue
            option = "Yes" if yn else "No"
            await sel.select_option(label=option)
        except Exception as e:  # noqa: BLE001
            log.debug("select skip: %s", e)

    radios = await page.query_selector_all("input[type=radio]")
    grouped: dict[str, list] = {}
    for r in radios:
        name = await r.get_attribute("name") or ""
        grouped.setdefault(name, []).append(r)
    for name, options in grouped.items():
        label_text = name
        try:
            fieldset = await options[0].evaluate_handle("e => e.closest('fieldset')")
            if fieldset:
                legend = await fieldset.evaluate("e => e.innerText || ''")
                label_text = legend or name
        except Exception:  # noqa: BLE001
            pass
        yn = _yes_no_match(label_text)
        if yn is None:
            continue
        for opt in options:
            opt_label = (
                await opt.get_attribute("value")
                or await opt.get_attribute("aria-label")
                or ""
            )
            if (yn and re.search(r"yes|true|1", opt_label, re.I)) or (
                not yn and re.search(r"no|false|0", opt_label, re.I)
            ):
                try:
                    await opt.check()
                except Exception:  # noqa: BLE001
                    pass
                break


async def _upload_resume(page: Page) -> None:
    if not RESUME_PDF.exists():
        log.warning("Resume PDF missing at %s; skipping upload", RESUME_PDF)
        return
    file_inputs = await page.query_selector_all("input[type=file]")
    for fi in file_inputs:
        try:
            await fi.set_input_files(str(RESUME_PDF))
            await _human_pause(short=True)
        except Exception as e:  # noqa: BLE001
            log.debug("file upload skip: %s", e)


async def _paste_cover_letter(page: Page, cover: str) -> None:
    if not cover:
        return
    texts = await page.query_selector_all("textarea")
    for ta in texts:
        try:
            label = (
                await ta.get_attribute("aria-label")
                or await ta.get_attribute("name")
                or await ta.get_attribute("placeholder")
                or ""
            )
            if re.search(r"cover|message|why|introduc", label, re.I):
                await ta.fill(cover)
                await _human_pause(short=True)
                return
        except Exception:  # noqa: BLE001
            pass


async def _try_click(page: Page, selectors: list[str]) -> bool:
    for sel in selectors:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await _human_pause(short=True)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


async def _detect_captcha(page: Page) -> bool:
    sels = [
        "iframe[src*='captcha']",
        "iframe[title*='captcha' i]",
        "div[class*='captcha' i]",
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
    ]
    for s in sels:
        try:
            if await page.query_selector(s):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


async def _linkedin_login(page: Page) -> None:
    await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
    if "/feed" in page.url:
        return
    if not (LINKEDIN_EMAIL and LINKEDIN_PASSWORD):
        return
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
    await page.fill("input#username", LINKEDIN_EMAIL)
    await page.fill("input#password", LINKEDIN_PASSWORD)
    await page.click("button[type=submit]")
    try:
        await page.wait_for_url("**/feed/**", timeout=20000)
    except Exception:  # noqa: BLE001
        pass


async def _apply_linkedin(page: Page, job: dict) -> tuple[bool, str]:
    await _linkedin_login(page)
    await page.goto(job["url"], wait_until="domcontentloaded")
    await _human_pause()

    clicked = await _try_click(page, [
        "button.jobs-apply-button",
        "button:has-text('Easy Apply')",
    ])
    if not clicked:
        return False, "Easy Apply not available"

    for step in range(8):
        if await _detect_captcha(page):
            return False, "CAPTCHA detected"
        await _fill_form_fields(page)
        await _upload_resume(page)
        await _paste_cover_letter(page, job.get("cover_letter", ""))
        if await _try_click(page, [
            "button:has-text('Submit application')",
            "button[aria-label*='Submit application' i]",
        ]):
            await _human_pause()
            return True, "submitted"
        if not await _try_click(page, [
            "button:has-text('Review')",
            "button:has-text('Next')",
            "button[aria-label*='Continue' i]",
            "button[aria-label*='Next' i]",
        ]):
            break
    return False, f"stalled after {step + 1} steps"


async def _apply_indeed(page: Page, job: dict) -> tuple[bool, str]:
    await page.goto(job["url"], wait_until="domcontentloaded")
    await _human_pause()
    clicked = await _try_click(page, [
        "button#indeedApplyButton",
        "button:has-text('Apply now')",
        "a:has-text('Apply now')",
    ])
    if not clicked:
        return False, "Apply button not found"

    for _ in range(8):
        if await _detect_captcha(page):
            return False, "CAPTCHA detected"
        await _fill_form_fields(page)
        await _upload_resume(page)
        await _paste_cover_letter(page, job.get("cover_letter", ""))
        if await _try_click(page, [
            "button:has-text('Submit your application')",
            "button:has-text('Submit application')",
            "button[type=submit]:has-text('Submit')",
        ]):
            return True, "submitted"
        if not await _try_click(page, [
            "button:has-text('Continue')",
            "button:has-text('Next')",
        ]):
            break
    return False, "stalled"


async def _apply_external(page: Page, job: dict) -> tuple[bool, str]:
    await page.goto(job["url"], wait_until="domcontentloaded")
    await _human_pause()
    await _try_click(page, [
        "a:has-text('Apply')",
        "button:has-text('Apply')",
        "a:has-text('Apply now')",
    ])
    await _human_pause()
    if await _detect_captcha(page):
        return False, "CAPTCHA detected"
    await _fill_form_fields(page)
    await _upload_resume(page)
    await _paste_cover_letter(page, job.get("cover_letter", ""))
    if await _try_click(page, [
        "button[type=submit]:has-text('Submit')",
        "button:has-text('Submit application')",
        "button:has-text('Send application')",
    ]):
        return True, "submitted"
    return False, "could not find submit"


async def _screenshot(page: Page, job_id: int) -> str:
    name = f"job_{job_id}_{int(time.time())}.png"
    path = SCREENSHOT_DIR / name
    try:
        await page.screenshot(path=str(path), full_page=True)
    except Exception as e:  # noqa: BLE001
        log.debug("screenshot failed: %s", e)
    return str(path)


async def apply_to_job(page: Page, job: dict) -> tuple[bool, str, str]:
    platform = (job.get("platform") or "").lower()
    if platform == "linkedin":
        ok, msg = await _apply_linkedin(page, job)
    elif platform == "indeed":
        ok, msg = await _apply_indeed(page, job)
    else:
        ok, msg = await _apply_external(page, job)
    shot = await _screenshot(page, job["id"])
    return ok, msg, shot


async def apply_many(jobs: list[dict], progress=None) -> None:
    """Run sequentially. `progress(done, total, job)` optional callback."""
    if not jobs:
        return
    total = len(jobs)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        storage = SESSION_DIR / "applicator.json"
        ctx_kwargs: dict = {"viewport": {"width": 1366, "height": 900}}
        if storage.exists():
            ctx_kwargs["storage_state"] = str(storage)
        context = await browser.new_context(**ctx_kwargs)
        page = await context.new_page()

        for i, job in enumerate(jobs, 1):
            log.info("Applying %d/%d: %s @ %s", i, total, job["title"], job["company"])
            try:
                ok, msg, shot = await apply_to_job(page, job)
                if ok:
                    update_status(job["id"], "applied", screenshot_path=shot)
                    log.info("Applied: %s @ %s", job["title"], job["company"])
                else:
                    update_status(job["id"], "failed", screenshot_path=shot, error_message=msg)
                    log.warning("Failed: %s @ %s — %s", job["title"], job["company"], msg)
            except Exception as e:  # noqa: BLE001
                log.exception("apply exception")
                update_status(job["id"], "failed", error_message=str(e))

            if progress:
                try:
                    progress(i, total, job)
                except Exception:  # noqa: BLE001
                    pass

            if i < total:
                await asyncio.sleep(APPLY_DELAY_SECONDS)

        try:
            await context.storage_state(path=str(storage))
        except Exception:  # noqa: BLE001
            pass
        await context.close()
        await browser.close()


def run_apply_many(job_ids: list[int]) -> None:
    """Sync entrypoint used by the Flask thread."""
    from db import get_job

    jobs = [get_job(jid) for jid in job_ids]
    jobs = [j for j in jobs if j]
    if not jobs:
        return
    log.info("Starting batch apply of %d jobs at %s", len(jobs), datetime.utcnow().isoformat())
    asyncio.run(apply_many(jobs))
