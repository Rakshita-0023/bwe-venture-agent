from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = DATA_DIR / "reports"
CHROMA_DIR = DATA_DIR / "chroma_db"

PAGES_PATH = PROCESSED_DIR / "pages.json"
VENTURES_PATH = PROCESSED_DIR / "ventures.json"
BLOGS_PATH = PROCESSED_DIR / "blogs.json"
PERSONAL_ALIGNMENT_PATH = PROCESSED_DIR / "personal_alignment.json"
PERSONAL_PROFILE_PATH = DATA_DIR / "personal_profile.md"

BASE_URL = "https://boldworldengineering.com/"
ALLOWED_DOMAINS = {
    "boldworldengineering.com",
    "www.boldworldengineering.com",
    "bwestudios.com",
    "www.bwestudios.com",
}
USER_AGENT = "BWE-Venture-Intelligence-Agent/1.0 (+local internship project)"
REQUEST_DELAY_SECONDS = float(os.getenv("BWE_REQUEST_DELAY_SECONDS", "1.0"))
MAX_PAGES = int(os.getenv("BWE_MAX_PAGES", "40"))
OLLAMA_MODEL = os.getenv("BWE_OLLAMA_MODEL", "llama3.1")
OLLAMA_EMBED_MODEL = os.getenv("BWE_OLLAMA_EMBED_MODEL", "nomic-embed-text")
COLLECTION_NAME = "bwe_pages"
SUPABASE_URL = "https://mzpwsxboizcuvndlhvsd.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im16cHdzeGJvaXpjdXZuZGxodnNkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM3MzY5NzYs"
    "ImV4cCI6MjA3OTMxMjk3Nn0.Dbmd_Il3APn3mYkAOf9Rl_S93Kja_jmiRQcBaGFl1xw"
)

PRIORITY_KEYWORDS = [
    "venture",
    "portfolio",
    "product",
    "company",
    "blog",
    "insight",
    "case",
    "about",
    "thesis",
    "mission",
    "builder",
    "backer",
    "believer",
]

REPORT_FILES = {
    "overview": REPORTS_DIR / "bwe_overview.md",
    "ventures": REPORTS_DIR / "venture_list.md",
    "blogs": REPORTS_DIR / "blog_insights.md",
    "thesis": REPORTS_DIR / "product_fit_and_thesis.md",
    "alignment": REPORTS_DIR / "personal_venture_alignment.md",
    "style_guide": REPORTS_DIR / "bwe_voice_style_guide.md",
}
