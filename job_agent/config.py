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

# Job search targeting
TARGET_ROLES = [
    "Data Scientist",
    "AI Engineer",
    "Machine Learning Engineer",
    "Business Intelligence Analyst",
    "Data Analyst",
    "AI Automation Engineer",
    "Forward Deployment Engineer",
    "ML Analyst",
    "Analytics Engineer",
    "AI Product Analyst",
    "Data Science Intern",
    "AI Research Analyst",
]

LOCATIONS = [
    "Remote",
    "Dallas TX",
    "Plano TX",
    "Irving TX",
    "Frisco TX",
    "McKinney TX",
    "Richardson TX",
    "DFW",
]

WORK_TYPES = ["remote", "part-time", "hybrid"]

# Pipeline knobs
MIN_FIT_SCORE = 70
APPLY_DELAY_SECONDS = 45
MAX_JOBS_PER_RUN = 50
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
