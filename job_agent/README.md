# Job Application Agent

Automated job search, Claude-scored fit, one-click batch apply.

The agent searches LinkedIn / Indeed / Glassdoor for the roles in `config.py`, scores each listing against `resume.txt` using Claude, and shows the matches above a fit threshold in a local dashboard. You tick the boxes, hit **Apply to Selected**, and Playwright drives the applications.

## Setup

```bash
cd job_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env       # fill in ANTHROPIC_API_KEY and LinkedIn/Indeed creds
```

Place your resume PDF at `job_agent/resume.pdf` (used for uploads). The plain-text `resume.txt` is used for scoring; edit it to keep it current.

## Run

```bash
python agent.py
```

* Dashboard opens at <http://localhost:5000>.
* The pipeline runs daily at 8:00 AM and 6:00 PM (configurable in `config.py: SCHEDULE_HOURS`).
* **Run Search Now** in the dashboard triggers a manual run.
* **Auto-apply is ON by default** (`config.py: AUTO_APPLY = True`): after scoring, the agent submits every job above `MIN_FIT_SCORE` with no dashboard click. Set `AUTO_APPLY = False` if you want the human-in-the-loop "Apply to Selected" button instead.
* `APPLY_DELAY_SECONDS` (default 45s) spaces submissions apart so LinkedIn doesn't flag the account.

## How it works

```
agent.py
├── scrapers/{linkedin,indeed,glassdoor}.py  ← Playwright searches
├── scorer.py                                ← Claude scores + generates cover letter
├── db.py                                    ← SQLite storage
├── app.py + templates/dashboard.html        ← Flask dashboard
└── applicator.py                            ← Playwright auto-apply
```

## Notes

* LinkedIn blocks headless browsers, so scraping + applying run **headed**. The first run logs in interactively; cookies are cached in `.sessions/`.
* Random 2-5s pauses are inserted between actions.
* If a CAPTCHA appears, the application is marked **failed** with `error_message = "CAPTCHA detected"`. Open the job from the dashboard and finish it by hand.
* All activity goes to `logs/applications.log`; submission screenshots land in `logs/screenshots/`.
* The dashboard works without the agent running — it just shows whatever SQLite has.

## Config knobs (config.py)

| Setting | What it does |
| --- | --- |
| `TARGET_ROLES` | Search keywords cycled per platform |
| `LOCATIONS` | Locations cycled per role |
| `MIN_FIT_SCORE` | Below this, jobs are scored but not shown |
| `APPLY_DELAY_SECONDS` | Wait between submissions |
| `MAX_JOBS_PER_RUN` | Hard cap per pipeline run |
| `SCHEDULE_HOURS` | Hours of day (local) to auto-run |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` by default |

## Safety

* No credentials are committed (`.env` is in `.gitignore`).
* No PDF resume is committed (`resume.pdf` is in `.gitignore`).
* The SQLite DB and screenshots stay local.
