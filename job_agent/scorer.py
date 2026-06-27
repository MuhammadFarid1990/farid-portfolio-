"""Score a job against the resume with the Claude API."""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, RESUME_TXT

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a job fit scorer for a candidate with HARD CONSTRAINTS.

The candidate is a graduate student at UT Dallas (MS Business Analytics and AI, graduating May 2027). They are ONLY looking for:
1. Part-time, internship, co-op, contract, or working-student roles starting Fall 2026 (Aug-Dec 2026)
2. Location must be either:
   - Remote within the United States, OR
   - Onsite or hybrid in the Dallas / Fort Worth (DFW) metro area (Dallas, Plano, Irving, Frisco, McKinney, Richardson, Addison, Allen)
3. Data Science, ML, AI, Analytics, BI, or related quantitative roles

HARD-FILTER rules — if any apply, the score MUST be 0-20:
- Full-time only positions (no part-time option mentioned)
- Locations outside the US, including UK, EU, India, LATAM, Canada, Asia
- Roles requiring 3+ years of experience or senior/staff/principal/lead titles
- Onsite-only roles outside DFW (e.g. SF, NYC, Seattle, Austin, Boston)
- Roles in unrelated fields (sales, marketing, customer support, recruiting, finance ops)

If the job passes the hard filters, score on skill match:
- 70-89: strong skill match for Fall 2026 part-time / intern
- 90+: near-perfect match (explicit part-time / intern + Fall 2026 + remote-US or DFW + skills align)
- 40-69: borderline (e.g. relevant skills but unclear on part-time/Fall 2026)

Return ONLY a JSON object with:
- "score": integer 0-100
- "reason": one sentence explaining the score, naming the constraint that pushed it up or down
- "cover_letter": 3-paragraph cover letter in plain direct language, no AI-sounding phrases, no hyphens as dashes. Only generate if score >= 40, otherwise return empty string."""


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
