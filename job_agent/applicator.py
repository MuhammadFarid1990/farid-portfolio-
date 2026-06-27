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
    CANDIDATE_CITY,
    CANDIDATE_COUNTRY,
    CANDIDATE_DOB,
    CANDIDATE_EMAIL,
    CANDIDATE_LINKEDIN,
    CANDIDATE_NAME,
    CANDIDATE_PHONE,
    CANDIDATE_STATE,
    CANDIDATE_WEBSITE,
    CANDIDATE_ZIP,
    EEOC_DECLINE,
    HUMAN_DELAY_MAX,
    HUMAN_DELAY_MIN,
    JOB_BOARD_PASSWORD,
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
    (re.compile(r"first.?name|given.?name", re.I), CANDIDATE_NAME.split()[0]),
    (re.compile(r"last.?name|family.?name|surname", re.I), CANDIDATE_NAME.split()[-1]),
    (re.compile(r"full.?name|^name|legal.?name", re.I), CANDIDATE_NAME),
    (re.compile(r"e.?mail", re.I), CANDIDATE_EMAIL),
    (re.compile(r"phone|mobile|cell", re.I), CANDIDATE_PHONE),
    (re.compile(r"linkedin", re.I), CANDIDATE_LINKEDIN),
    (re.compile(r"website|portfolio|personal site|home.?page", re.I), CANDIDATE_WEBSITE),
    (re.compile(r"salary|compensation|desired.?pay", re.I), SALARY_EXPECTATION),
    (re.compile(r"city|town", re.I), CANDIDATE_CITY),
    (re.compile(r"state|province|region", re.I), CANDIDATE_STATE),
    (re.compile(r"zip|postal", re.I), CANDIDATE_ZIP),
    (re.compile(r"country|nation", re.I), CANDIDATE_COUNTRY),
    (re.compile(r"address.?line.?1|street", re.I), f"{CANDIDATE_CITY}, {CANDIDATE_STATE}"),
    (re.compile(r"birth|dob|date.?of.?birth", re.I), CANDIDATE_DOB),
]


REQUIRED_FIELDS_WE_LACK: list[re.Pattern] = []
if not CANDIDATE_DOB:
    REQUIRED_FIELDS_WE_LACK.append(re.compile(r"birth|dob|date.?of.?birth", re.I))


EEOC_PATTERNS = [
    re.compile(r"gender", re.I),
    re.compile(r"race|ethnic", re.I),
    re.compile(r"veteran", re.I),
    re.compile(r"disab", re.I),
    re.compile(r"hispanic|latino", re.I),
    re.compile(r"sexual orientation", re.I),
]

EEOC_DECLINE_VALUES = [
    "Prefer not to answer",
    "Decline to self-identify",
    "I do not wish to answer",
    "Decline to answer",
    "I don't wish to answer",
    "Prefer not to say",
]


YES_NO_FIELDS: list[tuple[re.Pattern, bool]] = [
    (re.compile(r"authoriz", re.I), WORK_AUTHORIZED_US),
    (re.compile(r"legally.*work|us.?citizen|permanent.?resident", re.I), WORK_AUTHORIZED_US),
    (re.compile(r"sponsor", re.I), REQUIRES_SPONSORSHIP),
    (re.compile(r"visa", re.I), REQUIRES_SPONSORSHIP),
]


def _label_match(label: str) -> str | None:
    for pat, value in FIELD_MAP:
        if pat.search(label) and value:
            return value
    return None


def _is_eeoc(label: str) -> bool:
    return any(p.search(label) for p in EEOC_PATTERNS)


def _needs_missing_field(label: str) -> bool:
    return any(p.search(label) for p in REQUIRED_FIELDS_WE_LACK)


def _yes_no_match(label: str) -> bool | None:
    for pat, value in YES_NO_FIELDS:
        if pat.search(label):
            return value
    return None


async def _fill_form_fields(page: Page) -> list[str]:
    """Walk every input/select/radio on the page, fill what we recognize.

    Returns a list of issue strings (e.g. ["missing dob"]). Empty = no issues.
    """
    issues: list[str] = []

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
            if input_type == "password":
                if JOB_BOARD_PASSWORD:
                    current = await el.input_value()
                    if not current:
                        await el.fill(JOB_BOARD_PASSWORD)
                        await _human_pause(short=True)
                else:
                    issues.append("password field but JOB_BOARD_PASSWORD not set")
                continue
            if _needs_missing_field(label):
                required = await el.get_attribute("required") or await el.get_attribute("aria-required")
                if required:
                    issues.append(f"missing required field: {label}")
                continue
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
            if EEOC_DECLINE and _is_eeoc(label):
                await _select_decline(sel)
                continue
            yn = _yes_no_match(label)
            if yn is not None:
                option = "Yes" if yn else "No"
                try:
                    await sel.select_option(label=option)
                except Exception:  # noqa: BLE001
                    pass
                continue
            text_val = _label_match(label)
            if text_val:
                try:
                    await sel.select_option(label=text_val)
                except Exception:  # noqa: BLE001
                    try:
                        await sel.select_option(value=text_val)
                    except Exception:  # noqa: BLE001
                        pass
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
        if EEOC_DECLINE and _is_eeoc(label_text):
            await _check_decline_radio(options)
            continue
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

    return issues


async def _select_decline(sel_handle) -> None:
    for label in EEOC_DECLINE_VALUES:
        try:
            await sel_handle.select_option(label=label)
            return
        except Exception:  # noqa: BLE001
            continue


async def _check_decline_radio(options: list) -> None:
    for opt in options:
        try:
            opt_label = (
                await opt.get_attribute("value")
                or await opt.get_attribute("aria-label")
                or ""
            )
            if re.search(r"decline|prefer.?not|do.?not.?wish|don'?t.?wish", opt_label, re.I):
                await opt.check()
                return
        except Exception:  # noqa: BLE001
            continue


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


async def _prefer_signup_tab(page: Page) -> None:
    """When a site shows Sign In / Sign Up tabs, click Sign Up so we create an account."""
    await _try_click(page, [
        "button:has-text('Create account')",
        "a:has-text('Create account')",
        "button:has-text('Sign up')",
        "a:has-text('Sign up')",
        "[data-test*='sign-up' i]",
        "[data-test*='signup' i]",
    ])


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


async def _apply_linkedin(page: Page, job: dict) -> tuple[bool, str, list[str]]:
    await _linkedin_login(page)
    await page.goto(job["url"], wait_until="domcontentloaded")
    await _human_pause()

    clicked = await _try_click(page, [
        "button.jobs-apply-button",
        "button:has-text('Easy Apply')",
    ])
    if not clicked:
        return False, "Easy Apply not available", []

    all_issues: list[str] = []
    for step in range(8):
        if await _detect_captcha(page):
            return False, "CAPTCHA detected", all_issues
        all_issues.extend(await _fill_form_fields(page))
        await _upload_resume(page)
        await _paste_cover_letter(page, job.get("cover_letter", ""))
        if await _try_click(page, [
            "button:has-text('Submit application')",
            "button[aria-label*='Submit application' i]",
        ]):
            await _human_pause()
            return True, "submitted", all_issues
        if not await _try_click(page, [
            "button:has-text('Review')",
            "button:has-text('Next')",
            "button[aria-label*='Continue' i]",
            "button[aria-label*='Next' i]",
        ]):
            break
    return False, f"stalled after {step + 1} steps", all_issues


async def _apply_indeed(page: Page, job: dict) -> tuple[bool, str, list[str]]:
    await page.goto(job["url"], wait_until="domcontentloaded")
    await _human_pause()
    clicked = await _try_click(page, [
        "button#indeedApplyButton",
        "button:has-text('Apply now')",
        "a:has-text('Apply now')",
    ])
    if not clicked:
        return False, "Apply button not found", []

    await _prefer_signup_tab(page)

    all_issues: list[str] = []
    for _ in range(8):
        if await _detect_captcha(page):
            return False, "CAPTCHA detected", all_issues
        all_issues.extend(await _fill_form_fields(page))
        await _upload_resume(page)
        await _paste_cover_letter(page, job.get("cover_letter", ""))
        if await _try_click(page, [
            "button:has-text('Submit your application')",
            "button:has-text('Submit application')",
            "button[type=submit]:has-text('Submit')",
        ]):
            return True, "submitted", all_issues
        if not await _try_click(page, [
            "button:has-text('Continue')",
            "button:has-text('Next')",
        ]):
            break
    return False, "stalled", all_issues


async def _apply_external(page: Page, job: dict) -> tuple[bool, str, list[str]]:
    await page.goto(job["url"], wait_until="domcontentloaded")
    await _human_pause()
    await _try_click(page, [
        "a:has-text('Apply')",
        "button:has-text('Apply')",
        "a:has-text('Apply now')",
    ])
    await _human_pause()
    if await _detect_captcha(page):
        return False, "CAPTCHA detected", []
    await _prefer_signup_tab(page)
    issues = await _fill_form_fields(page)
    await _upload_resume(page)
    await _paste_cover_letter(page, job.get("cover_letter", ""))
    if await _try_click(page, [
        "button[type=submit]:has-text('Submit')",
        "button:has-text('Submit application')",
        "button:has-text('Send application')",
    ]):
        return True, "submitted", issues
    return False, "could not find submit", issues


async def _screenshot(page: Page, job_id: int) -> str:
    name = f"job_{job_id}_{int(time.time())}.png"
    path = SCREENSHOT_DIR / name
    try:
        await page.screenshot(path=str(path), full_page=True)
    except Exception as e:  # noqa: BLE001
        log.debug("screenshot failed: %s", e)
    return str(path)


async def apply_to_job(page: Page, job: dict) -> tuple[bool, str, str, list[str]]:
    from config import ENABLED_PLATFORMS

    platform = (job.get("platform") or "").lower()
    if platform not in ENABLED_PLATFORMS:
        return False, f"platform '{platform}' disabled in config", "", []
    if platform == "linkedin":
        ok, msg, issues = await _apply_linkedin(page, job)
    elif platform == "indeed":
        ok, msg, issues = await _apply_indeed(page, job)
    else:
        ok, msg, issues = await _apply_external(page, job)
    shot = await _screenshot(page, job["id"])
    return ok, msg, shot, issues


def _classify_failure(msg: str, issues: list[str]) -> str:
    """Decide between 'failed' (genuine error) and 'needs_manual' (we just can't finish it)."""
    if issues:
        return "needs_manual"
    needs_manual_signals = (
        "CAPTCHA",
        "password field but JOB_BOARD_PASSWORD",
    )
    if any(s in msg for s in needs_manual_signals):
        return "needs_manual"
    return "failed"


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
                ok, msg, shot, issues = await apply_to_job(page, job)
                if ok:
                    update_status(job["id"], "applied", screenshot_path=shot)
                    log.info("Applied: %s @ %s", job["title"], job["company"])
                else:
                    status = _classify_failure(msg, issues)
                    detail = msg if not issues else f"{msg}; {'; '.join(issues)}"
                    update_status(job["id"], status, screenshot_path=shot, error_message=detail)
                    log.warning("%s: %s @ %s — %s", status, job["title"], job["company"], detail)
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
