# Where we left off — pick up here next session

Last worked on: 2026-06-26 evening.

## What's done and working

- Full project scaffolded under `job_agent/` and pushed to branch `claude/job-application-agent-528ny4`.
- User (Muhammad) has it running locally on Windows at `C:\Users\mfari\farid-portfolio-\job_agent\` inside a `.venv`.
- `.env` and `resume.pdf` are in place on his machine.
- Chromium is installed via `playwright install chromium`.
- First `python agent.py` ran successfully — Flask served on http://localhost:5000, scheduler armed for 8 AM / 6 PM.

## Settings that changed mid-session

- `AUTO_APPLY = True` — pipeline auto-submits after scoring, no dashboard click.
- `ENABLED_PLATFORMS = ["indeed", "glassdoor"]` — LinkedIn disabled for now (account safety).
- CSV export button added to dashboard (`/export.csv`).

## Half-finished work (NEXT SESSION starts here)

We were adding **signup-form handling** so the agent can create accounts on job boards that require it.

Already committed to `config.py` and `.env.example`:
- `CANDIDATE_CITY`, `CANDIDATE_STATE`, `CANDIDATE_ZIP`, `CANDIDATE_COUNTRY`
- `CANDIDATE_DOB` (optional)
- `JOB_BOARD_PASSWORD` (user needs to set in his local `.env`)
- `EEOC_DECLINE = True`

**Still TO DO:**
1. Teach `applicator.py` to detect signup pages (look for "Create account", "Sign up", password+confirm-password fields) and fill them using `JOB_BOARD_PASSWORD`.
2. Add a `needs_manual` job status for forms requiring fields we don't have (DOB if blank, etc.). Show these distinctly in the dashboard.
3. Detect EEOC questions (gender, race, veteran, disability) and select "Prefer not to answer" / "Decline to self-identify".
4. Extend the FIELD_MAP regex list in `applicator.py` to cover city/state/zip/country.

## User preferences captured

- Wants full auto-apply, no clicks (DONE).
- Wants LinkedIn skipped until further notice (DONE).
- Picked all three signup-field options: city/state/zip, DOB, EEOC auto-decline.
- Was about to set `JOB_BOARD_PASSWORD` in his local `.env`. He suggested `Sana123456!` — I pushed back as weak. He hadn't decided yet.

## Things to remind the user tomorrow

1. **Set `JOB_BOARD_PASSWORD` in his local `.env`** — pick something stronger than `Sana123456!`.
2. **He needs to `git pull` before restarting** — half-finished signup work will land in the next commit.
3. **Revoked Anthropic key already** (good). New key is in his local `.env`.

## Quick resume command for tomorrow

```
cd C:\Users\mfari\farid-portfolio-\job_agent
git pull
.venv\Scripts\activate
python agent.py
```
