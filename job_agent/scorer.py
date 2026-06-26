"""Score a job against the resume with the Claude API."""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, RESUME_TXT

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a job fit scorer. Given a job description and a candidate resume, return ONLY a JSON object with:
- "score": integer 0-100 representing how well the candidate fits this role
- "reason": exactly one sentence explaining the top reason for the score
- "cover_letter": a 3-paragraph cover letter tailored to this specific job, written in plain direct language, no AI-sounding phrases, no hyphens used as dashes

Score above 70 only if the role genuinely matches the candidate's skills and experience level.
Be strict. Partial matches score 50-69. Strong matches score 70-89. Near-perfect matches score 90+."""


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
