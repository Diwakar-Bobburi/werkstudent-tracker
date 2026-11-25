"""Central configuration. Edit KEYWORDS to change what gets tracked."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RUN_LOG = DATA_DIR / "runs.jsonl"

USER_AGENT = "werkstudent-tracker/0.2 (portfolio project; github.com/Diwakar-Bobburi/werkstudent-tracker)"

# --- Bundesagentur für Arbeit (Jobsuche) ---------------------------------
# Tried in order; the first that answers is used for the rest of the run.
# The API version changes without notice (v4 -> v6 in 2026), hence the fallback list.
BA_URLS = [
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs",
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v5/jobs",
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/app/jobs",
]
BA_API_KEY = "jobboerse-jobsuche"  # public client id used by the official web app
BA_PAGE_SIZE = 100
BA_MAX_PAGES = 50            # per keyword; broad search, so allow up to 5,000 postings
# Fetch the FULL open list every day (100 = API max), not just new postings.
# A posting that stops appearing has been taken down -> lets us measure how long postings stay open.
BA_PUBLISHED_SINCE_DAYS = 100
# Broad searches; relevance (AI/ML/Data) is decided client-side by STUDENT_TERMS + DOMAIN_TERMS,
# because combined phrases like "Werkstudent Data Science" match almost nothing.
BA_KEYWORDS = ["Werkstudent", "Working Student"]

# --- Arbeitnow ------------------------------------------------------------
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
ARBEITNOW_MAX_PAGES = 30
ARBEITNOW_LOOKBACK_DAYS = 90  # walk (almost) the whole board so we can see when postings disappear

# A posting counts as "Werkstudent" if its title matches one of these ...
STUDENT_TERMS = ["werkstudent", "working student", "studentische", "student assistant", "student job"]
# ... and its title or tags match one of these.
DOMAIN_TERMS = [
    "data", "machine learning", "ml", "ai", "ki", "künstliche intelligenz",
    "artificial intelligence", "analytics", "python", "nlp", "llm", "deep learning",
    "computer vision", "bi", "business intelligence", "statistik",
    "data science", "datenanalyse", "daten",
]

# --- HTTP -----------------------------------------------------------------
REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 1.0  # be polite: unofficial API, no rate-limit docs
