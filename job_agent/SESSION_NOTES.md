# Where we left off — pick up here next session

Last worked on: 2026-06-27 evening.

## Where the user is right now

Muhammad is running the agent on Windows at `C:\Users\mfari\farid-portfolio-\job_agent\` under a `.venv`, launched via `start.bat`. The Flask dashboard is at http://127.0.0.1:5000. He's pulled and restarted multiple times; the latest commit on `claude/job-application-agent-528ny4` is the three-section rework.

## What works

- 5 JSON-based job sources fully working: Remotive, Remote OK, Arbeitnow, The Muse, Greenhouse public boards. Indeed/LinkedIn/Glassdoor are kept in code but disabled because of Cloudflare.
- Claude scoring works (after he revoked two leaked API keys and added a third). He has ~$16 credit.
- Dashboard is now three sections (Auto-Apply / Manual Apply / Hiring Manager Contacts), light theme.
- Excel export with 4 sheets (Auto-Apply / Manual Apply / Hiring Managers / Applied history) via openpyxl.
- One-click "Pull & Restart" button works thanks to `start.bat` wrapper that loops on exit code 42.
- Auto-purge of non-US jobs on startup + manual "Purge Non-US" button.
- Hiring manager search links (Google → site:linkedin.com/in) per company.
- "Mark as applied ✓" button on manual rows.

## THE OPEN PROBLEM (start here tomorrow)

**Volume is still only ~5 matches per run.** User explicitly called this out: "After your next Run Search Now, you should see 30-80+ matches — this is not running, i still see 5".

I had bumped `MAX_JOBS_PER_RUN = 200` and broadened `TARGET_ROLES` to common phrases like "data analyst", "data scientist", "intern", but the real bottleneck is somewhere else. Likely causes to investigate IN THIS ORDER:

1. **The five JSON sources may not return many real matches for the strict scorer.** Claude's hard rules (in `scorer.py` SYSTEM_PROMPT) require part-time / intern / Fall 2026 / US-only — most senior or full-time jobs auto-score 0-20 and get filtered out by `MIN_FIT_SCORE = 25`. Check the terminal logs to see how many jobs are being scraped vs how many score 25+.
2. **Remotive / Remote OK return mostly senior or non-relevant titles** even when filtered by keyword. The `_is_non_us_location` filter catches lots more than expected (London, Bangalore, etc.) — could be dropping legitimate US-remote roles where the location string is ambiguous.
3. **The role keyword filter is `t in title.lower()`** — too restrictive. A job titled "Senior Data Engineer, Platform" doesn't contain "data analyst" or "data scientist". Should probably do tokenized matching ("data" + "scientist") or use a broader OR.
4. **Greenhouse company list is short (~25 companies).** Could expand to 100+ and also add Lever boards (api.lever.co/v0/postings/{slug}).

Suggested fix path tomorrow:
- Add `LeverScraper` (lever.co public board API)
- Triple the Greenhouse company list
- Loosen role matching (tokenize)
- Add detailed counter logging: "Remotive: 312 raw → 47 matched keyword → 12 passed location → 3 scored 25+"
- Maybe relax `MIN_FIT_SCORE` to 15 since the hard-rule filter does the heavy lifting

## Settings that diverge from defaults

- `AUTO_APPLY = True`
- `ENABLED_PLATFORMS = ["remotive", "remoteok", "arbeitnow", "themuse", "greenhouse"]`
- `MIN_FIT_SCORE = 25`
- `MAX_JOBS_PER_RUN = 200`
- `APPLY_DELAY_SECONDS = 30`
- `MIN_FIT_SCORE = 25`
- `TARGET_ROLES` — broad keywords ("data analyst", "data scientist", "machine learning", "intern", etc.)
- `LOCATIONS = ["Remote", "United States", "Dallas TX", "DFW"]`

## Signup-handling config the user added to his local .env

He added (or should have added) on his side, not in git:
```
JOB_BOARD_PASSWORD=...
CANDIDATE_CITY=Dallas
CANDIDATE_STATE=TX
CANDIDATE_ZIP=75080
CANDIDATE_COUNTRY=United States
CANDIDATE_DOB=
```

## Things to remind the user tomorrow

1. **Stop pasting API keys / passwords in chat.** He's done it twice now. Both keys had to be revoked.
2. Auto-apply success rate on external company sites is realistically 20-30%. Most postings will end up in the Manual Apply section. That's a feature, not a bug — the dashboard surfaces them and he applies in 2 minutes each.
3. He has `$16` credit on Anthropic. Each pipeline run scores 100-200 jobs ≈ $0.30–$0.60. Should last weeks.

## Quick resume command

```
cd C:\Users\mfari\farid-portfolio-\job_agent
start.bat
```

(Or just click "Pull & Restart" in the dashboard if it's already open.)

## When resuming, say to me

"Continue from SESSION_NOTES.md — focus on getting the volume above 5 matches."

That's the single thing to fix tomorrow.
