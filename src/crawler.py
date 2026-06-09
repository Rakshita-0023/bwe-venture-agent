from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from collections import deque
from typing import Any
from urllib.parse import urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup

from config import (
    BASE_URL,
    MAX_PAGES,
    PAGES_PATH,
    PRIORITY_KEYWORDS,
    RAW_DIR,
    REQUEST_DELAY_SECONDS,
    SUPABASE_ANON_KEY,
    SUPABASE_URL,
    USER_AGENT,
)
from utils import (
    ensure_directories,
    normalize_whitespace,
    safe_filename,
    save_json,
    should_skip_url,
    to_absolute_url,
)


def _request_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Accept": "application/json",
    }


def _fetch_robots(session: requests.Session) -> tuple[list[str], list[str]]:
    robots_url = to_absolute_url("/robots.txt", BASE_URL)
    try:
        response = session.get(robots_url, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return [], []

    disallowed: list[str] = []
    sitemaps: list[str] = []
    for line in response.text.splitlines():
        line = line.strip()
        if line.lower().startswith("disallow:"):
            value = line.split(":", 1)[1].strip()
            if value:
                disallowed.append(value)
        if line.lower().startswith("sitemap:"):
            value = line.split(":", 1)[1].strip()
            if value:
                sitemaps.append(value)
    return disallowed, sitemaps


def _load_sitemap_urls(session: requests.Session, sitemap_url: str) -> list[str]:
    try:
        response = session.get(sitemap_url, timeout=20)
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except Exception:
        return []

    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [node.text.strip() for node in root.findall(".//sm:loc", namespace) if node.text]
    return urls


def _is_allowed_by_robots(url: str, disallowed_paths: list[str]) -> bool:
    path = urlparse(url).path or "/"
    return not any(path.startswith(rule) for rule in disallowed_paths if rule != "/")


def _page_priority(url: str) -> tuple[int, int, str]:
    lowered = url.lower()
    matched = sum(1 for keyword in PRIORITY_KEYWORDS if keyword in lowered)
    home_bias = 1 if lowered.rstrip("/") == BASE_URL.rstrip("/") else 0
    return (-matched, -home_bias, lowered)


def _page_type(url: str, title: str, text: str) -> str:
    haystack = f"{url} {title} {text[:800]}".lower()
    if any(keyword in haystack for keyword in ["blog", "insight", "article"]):
        return "blog"
    if any(keyword in haystack for keyword in ["case study", "case-studies"]):
        return "case_study"
    if any(keyword in haystack for keyword in ["venture", "portfolio", "product", "company"]):
        return "venture"
    if any(keyword in haystack for keyword in ["thesis", "mission", "about", "builder", "backer", "believer"]):
        return "about"
    return "general"


def _extract_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute = to_absolute_url(anchor["href"], page_url)
        absolute = absolute.split("#", 1)[0]
        if should_skip_url(absolute) or absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)
    return links


def _extract_content(url: str, html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = normalize_whitespace(soup.title.get_text(" ", strip=True) if soup.title else "")
    markdown = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_links=True,
        include_images=False,
        include_formatting=True,
    ) or ""
    text = trafilatura.extract(
        html,
        url=url,
        output_format="txt",
        include_links=False,
        include_images=False,
    ) or normalize_whitespace(soup.get_text(" ", strip=True))
    if not title:
        h1 = soup.find("h1")
        title = normalize_whitespace(h1.get_text(" ", strip=True) if h1 else urlparse(url).path.strip("/"))
    links = _extract_links(html, url)
    return {
        "url": url,
        "title": title or "untitled",
        "page_type": _page_type(url, title, text),
        "text": normalize_whitespace(text),
        "markdown": markdown.strip(),
        "links": links,
    }


def _save_raw_html(url: str, html: str) -> None:
    parsed = urlparse(url)
    path_hint = parsed.path.strip("/") or "home"
    filename = safe_filename(f"{parsed.netloc}-{path_hint}", ".html")
    (RAW_DIR / filename).write_text(html, encoding="utf-8")


def _save_raw_json(name: str, payload: Any) -> None:
    (RAW_DIR / safe_filename(name, ".json")).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _rest_query(session: requests.Session, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    response = session.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=_supabase_headers(),
        params=params,
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _make_markdown(title: str, sections: list[tuple[str, Any]]) -> str:
    lines = [f"# {title}", ""]
    for heading, value in sections:
        if value in (None, "", [], {}):
            continue
        lines.append(f"## {heading}")
        if isinstance(value, list):
            for item in value:
                lines.append(f"- {item}")
        else:
            lines.append(str(value))
        lines.append("")
    return "\n".join(lines).strip()


def _make_text(sections: list[tuple[str, Any]]) -> str:
    parts: list[str] = []
    for heading, value in sections:
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            parts.append(f"{heading}: {', '.join(str(item) for item in value)}")
        else:
            parts.append(f"{heading}: {value}")
    return normalize_whitespace(" ".join(parts))


def _api_pages() -> list[dict[str, Any]]:
    session = _request_session()
    pages: list[dict[str, Any]] = []

    ventures = _rest_query(
        session,
        "ventures",
        {"select": "*", "is_public": "eq.true", "order": "order_index.asc,name.asc"},
    )
    _save_raw_json("supabase-ventures", ventures)
    for venture in ventures:
        title = venture.get("name") or "Unknown Venture"
        sections = [
            ("Tagline", venture.get("tagline")),
            ("Description", venture.get("description")),
            ("Vertical", venture.get("vertical") or venture.get("category")),
            ("Status", venture.get("status")),
            ("Problem Statement", venture.get("problem_statement")),
            ("Solution", venture.get("solution")),
            ("Ideal Customer Profile", venture.get("icp")),
            ("Market Traction", venture.get("market_traction")),
            ("Technology Stack", venture.get("technology_stack") or []),
            ("Website", venture.get("website_url")),
        ]
        slug = venture.get("slug") or safe_filename(title)
        pages.append(
            {
                "url": f"https://bwestudios.com/ventures/{slug}",
                "title": title,
                "page_type": "venture",
                "text": _make_text(sections),
                "markdown": _make_markdown(title, sections),
                "links": [link for link in [venture.get("website_url")] if link],
            }
        )

    case_studies = _rest_query(session, "case_studies", {"select": "*", "order": "date_published.desc,title.asc"})
    _save_raw_json("supabase-case-studies", case_studies)
    for case_study in case_studies:
        title = case_study.get("title") or "Untitled Case Study"
        sections = [
            ("Excerpt", case_study.get("excerpt")),
            ("Challenge", case_study.get("challenge")),
            ("Solution", case_study.get("solution")),
            ("Implementation", case_study.get("implementation")),
            ("Results", case_study.get("results")),
            ("Lessons Learned", case_study.get("lessons_learned")),
            ("Metrics", case_study.get("metrics")),
            ("Primary CTA", case_study.get("primary_cta")),
            ("Content Intent", case_study.get("content_intent")),
        ]
        slug = case_study.get("slug") or safe_filename(title)
        pages.append(
            {
                "url": f"https://bwestudios.com/case-studies/{slug}",
                "title": title,
                "page_type": "case_study",
                "text": _make_text(sections),
                "markdown": _make_markdown(title, sections),
                "links": [],
            }
        )

    blog_posts = _rest_query(
        session,
        "blog_posts",
        {"select": "*", "published": "eq.true", "order": "date_published.desc"},
    )
    _save_raw_json("supabase-blog-posts", blog_posts)
    for post in blog_posts:
        title = post.get("title") or "Untitled Post"
        sections = [
            ("Category", post.get("category")),
            ("Author", post.get("author")),
            ("Excerpt", post.get("excerpt")),
            ("Content", post.get("content")),
            ("Tags", post.get("tags") or []),
            ("Content Intent", post.get("content_intent")),
            ("Target Keyword", post.get("target_keyword")),
            ("Money Page Target", post.get("money_page_target")),
        ]
        slug = post.get("slug") or safe_filename(title)
        pages.append(
            {
                "url": f"https://bwestudios.com/hub/{slug}",
                "title": title,
                "page_type": "blog",
                "text": _make_text(sections),
                "markdown": _make_markdown(title, sections),
                "links": [],
            }
        )

    return pages


def _crawl_with_requests() -> list[dict[str, Any]]:
    session = _request_session()
    disallowed_paths, sitemap_urls = _fetch_robots(session)
    seed_urls = {BASE_URL, "https://bwestudios.com/"}
    for sitemap_url in sitemap_urls:
        seed_urls.update(_load_sitemap_urls(session, sitemap_url))

    queue = deque(sorted(seed_urls, key=_page_priority))
    visited: set[str] = set()
    pages: list[dict[str, Any]] = []

    while queue and len(pages) < MAX_PAGES:
        url = queue.popleft().split("#", 1)[0]
        if url in visited or should_skip_url(url) or not _is_allowed_by_robots(url, disallowed_paths):
            continue

        visited.add(url)
        try:
            response = session.get(url, timeout=25)
            response.raise_for_status()
        except requests.RequestException:
            continue

        if "text/html" not in response.headers.get("content-type", ""):
            continue

        html = response.text
        _save_raw_html(url, html)
        page = _extract_content(url, html)
        if page["text"] or page["markdown"]:
            pages.append(page)

        for link in sorted(page["links"], key=_page_priority):
            if link not in visited and not should_skip_url(link):
                queue.append(link)

        time.sleep(REQUEST_DELAY_SECONDS)

    pages.sort(key=lambda item: _page_priority(item["url"]))
    return pages


def _crawl_with_crawl4ai() -> list[dict[str, Any]]:
    try:
        from crawl4ai import AsyncWebCrawler
    except Exception:
        return []

    # Crawl4AI support can vary across local environments. The requests/trafilatura
    # path remains the default stable crawler; this hook exists for stack alignment.
    _ = AsyncWebCrawler
    return []


def run_crawl() -> None:
    ensure_directories()
    html_pages = _crawl_with_crawl4ai() or _crawl_with_requests()
    api_pages = _api_pages()
    merged: dict[str, dict[str, Any]] = {}
    for page in html_pages + api_pages:
        current = merged.get(page["url"])
        if current is None or len(page.get("text", "")) > len(current.get("text", "")):
            merged[page["url"]] = page
    pages = sorted(merged.values(), key=lambda item: (_page_priority(item["url"]), item["title"]))
    save_json(PAGES_PATH, pages)
    print(f"Saved {len(pages)} pages to {PAGES_PATH}")
