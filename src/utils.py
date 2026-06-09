from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from config import ALLOWED_DOMAINS, CHROMA_DIR, DATA_DIR, PROCESSED_DIR, RAW_DIR, REPORTS_DIR


def ensure_directories() -> None:
    for path in [DATA_DIR, RAW_DIR, PROCESSED_DIR, REPORTS_DIR, CHROMA_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return cleaned or "item"


def safe_filename(text: str, suffix: str = "") -> str:
    name = slugify(text)[:80]
    return f"{name}{suffix}"


def to_absolute_url(url: str, base_url: str) -> str:
    return urljoin(base_url, url)


def is_internal_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.lower() in ALLOWED_DOMAINS


def should_skip_url(url: str) -> bool:
    lowered = url.lower()
    blocked_prefixes = ["/api/", "/wp-admin", "/cdn-cgi/"]
    blocked_extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".svg",
        ".webp",
        ".pdf",
        ".zip",
        ".mp4",
        ".webm",
        ".css",
        ".js",
        ".ico",
        ".xml",
    )
    parsed = urlparse(url)
    if not is_internal_url(url):
        return True
    if any(parsed.path.startswith(prefix) for prefix in blocked_prefixes):
        return True
    if parsed.path.lower().endswith(blocked_extensions):
        return True
    return False
