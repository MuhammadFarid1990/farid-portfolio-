"""Score a job against the resume with the Claude API."""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, RESUME_TXT

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a job fit scorer for a candidate applying to data/analytics/AI roles.

The candidate: MS Business Analytics & AI student at UT Dallas, graduating May 2027.
Skills: Python, SQL, machine learning, data science, business intelligence, AI/ML tools.
Availability: Part-time, internship, co-op, contract, OR flexible remote full-time.
Location: Remote (US) or onsite/hybrid in Dallas-Fort Worth (DFW) metro.

HARD REJECTION — score 0-15 only when ALL of these apply:
- Requires 5+ years experience OR explicitly "senior/staff/principal/lead/director" AND no junior path
- Location is non-US (UK, EU, India, Canada, LATAM, Asia) with no remote option
- Completely unrelated field (pure sales quota, customer support, manual QA, finance ops, HR, legal)

SOFT FACTORS — use these to set the score in 20-90 range:
- Explicitly part-time / intern / co-op / contract → big positive (+20)
- Explicitly remote-US or DFW → positive (+15)
- Entry-level / 0-2 years experience required → positive (+10)
- Good skill match (Python, SQL, ML, analytics) → positive (+10 to +20)
- Full-time but entry-level remote → neutral (still score 35-55, candidate may apply)
- Full-time with senior requirements → negative (score 15-30)
- 1-3 years experience required → slight negative

Score guide:
- 75-95: explicit intern/part-time + right location + strong skill match
- 55-74: good skill match, right location, unclear or flexible on hours
- 35-54: right field and location, full-time entry-level (candidate can still apply)
- 20-34: borderline (some mismatch in experience or location)
- 0-19: clear hard rejection

Return ONLY a JSON object with:
- "score": integer 0-100
- "reason": one sentence explaining the score, naming the key factor
- "cover_letter": 3-paragraph cover letter in plain direct language, no AI-sounding phrases, no hyphens as dashes. Only generate if score >= 35, otherwise return empty string."""


@lru_cache(maxsize=1)
def _resume_text() -> str:
    if RESUME_TXT.exists():
        return RESUME_TXT.read_text(encoding="utf-8").strip()
    return ""


@lru_cache(maxsize=1)
def _client() -> Anthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return Anthropic(api_key=ANTHROPIC_API_KEY)


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM reply."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def score_job(job: dict) -> dict:
    """Return {score, reason, cover_letter}. Falls back to 0 on failure."""
    user_msg = (
        f"RESUME:\n{_resume_text()}\n\n"
        f"JOB TITLE: {job.get('title','')}\n"
        f"COMPANY: {job.get('company','')}\n"
        f"LOCATION: {job.get('location','')}\n"
        f"JOB DESCRIPTION:\n{job.get('description','')}"
    )
    try:
        resp = _client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        data = _extract_json(text)
        return {
            "score": int(data.get("score", 0)),
            "reason": str(data.get("reason", "")).strip(),
            "cover_letter": str(data.get("cover_letter", "")).strip(),
        }
    except Exception as e:  # noqa: BLE001
        log.error("Scoring failed for %s @ %s: %s", job.get("title"), job.get("company"), e)
        return {"score": 0, "reason": f"scoring error: {e}", "cover_letter": ""}
