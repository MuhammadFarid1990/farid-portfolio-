"""All settings in one place. Edit here to retarget the agent."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent
RESUME_TXT = PROJECT_ROOT / "resume.txt"
RESUME_PDF = PROJECT_ROOT / "resume.pdf"
DB_PATH = PROJECT_ROOT / "job_agent.db"
LOG_DIR = PROJECT_ROOT / "logs"
SCREENSHOT_DIR = LOG_DIR / "screenshots"
LOG_FILE = LOG_DIR / "applications.log"
SESSION_DIR = PROJECT_ROOT / ".sessions"

for p in (LOG_DIR, SCREENSHOT_DIR, SESSION_DIR):
    p.mkdir(parents=True, exist_ok=True)

# Candidate profile
CANDIDATE_NAME = "Muhammad Farid"
CANDIDATE_EMAIL = "Muhammad.farid@utdallas.edu"
CANDIDATE_PHONE = "704-819-1795"
CANDIDATE_LINKEDIN = "https://www.linkedin.com/in/muhammadfaridd"
CANDIDATE_GITHUB = "https://github.com/MuhammadFarid1990"
CANDIDATE_WEBSITE = "https://farid-portfoli0.vercel.app"
CANDIDATE_CITY = os.getenv("CANDIDATE_CITY", "Dallas")
CANDIDATE_STATE = os.getenv("CANDIDATE_STATE", "TX")
CANDIDATE_ZIP = os.getenv("CANDIDATE_ZIP", "75080")
CANDIDATE_COUNTRY = os.getenv("CANDIDATE_COUNTRY", "United States")
CANDIDATE_DOB = os.getenv("CANDIDATE_DOB", "")  # YYYY-MM-DD, optional
JOB_BOARD_PASSWORD = os.getenv("JOB_BOARD_PASSWORD", "")  # used when a site forces signup
EEOC_DECLINE = True  # auto-pick "prefer not to answer" on demographic questions

# Job search targeting
TARGET_ROLES = [
    "Data Science Intern",
    "Data Analyst Intern",
    "Machine Learning Intern",
    "AI Engineer Intern",
    "Business Intelligence Intern",
    "Analytics Intern",
    "Part-time Data Analyst",
    "Part-time Data Scientist",
    "Part-time AI Engineer",
    "Part-time Machine Learning Engineer",
    "Fall 2026 Data Science",
    "Fall 2026 Analytics",
    "Co-op Data Science",
    "Working Student Data",
]

LOCATIONS = [
    "Remote",
    "United States",
    "Dallas TX",
    "DFW",
]

WORK_TYPES = ["remote", "part-time", "internship"]

# Pipeline knobs
MIN_FIT_SCORE = 25  # Claude auto-scores irrelevant jobs at 0-20 via hard rules in the prompt; 25+ = relevant
APPLY_DELAY_SECONDS = 45
MAX_JOBS_PER_RUN = 50
AUTO_APPLY = True  # if True, pipeline applies right after scoring with no dashboard click

# Which platforms to scrape.
# JSON-API scrapers (no auth, no anti-bot, fast, reliable):
#   "remotive"   — remote tech jobs
#   "remoteok"   — high-volume remote
#   "arbeitnow"  — global remote/onsite mix
#   "themuse"    — US tech roles in remote-friendly companies
#   "greenhouse" — Stripe / Airbnb / Datadog / Anthropic / etc. public boards
#
# Playwright scrapers (fragile, fight Cloudflare, often return 0):
#   "linkedin", "indeed", "glassdoor"  — only enable if you accept the flakiness
ENABLED_PLATFORMS = ["remotive", "remoteok", "arbeitnow", "themuse", "greenhouse"]

# Hard cap on time a single scraper can run before we give up on it (seconds).
SCRAPER_TIMEOUT = 180
SCRAPE_TIMEOUT_SECONDS = 60
HUMAN_DELAY_MIN = 2
HUMAN_DELAY_MAX = 5

# Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# Platform credentials
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")
INDEED_EMAIL = os.getenv("INDEED_EMAIL", "")
INDEED_PASSWORD = os.getenv("INDEED_PASSWORD", "")

# Flask
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000

# Scheduler (24h clock, local time)
SCHEDULE_HOURS = [8, 18]

# Work authorization (used by applicator)
WORK_AUTHORIZED_US = True
REQUIRES_SPONSORSHIP = False
SALARY_EXPECTATION = "Open to discussion"
