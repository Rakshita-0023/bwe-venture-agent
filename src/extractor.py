from __future__ import annotations

import re
from typing import Any

from config import BLOGS_PATH, VENTURES_PATH
from utils import load_json, normalize_whitespace, save_json


def _unknown(value: Any) -> str:
    if value in (None, "", [], {}):
        return "unknown"
    if isinstance(value, str):
        cleaned = normalize_whitespace(value)
        return cleaned or "unknown"
    return str(value)


def _list_or_unknown(value: Any) -> list[str] | str:
    if not value:
        return "unknown"
    if isinstance(value, list):
        cleaned = [normalize_whitespace(str(item)) for item in value if normalize_whitespace(str(item))]
        return cleaned or "unknown"
    return [normalize_whitespace(str(value))]


def _summarize_text(text: str, max_sentences: int = 2) -> str:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return "unknown"
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    return " ".join(sentences[:max_sentences]).strip() or "unknown"


def _extract_key_points(content: str, limit: int = 4) -> list[str]:
    if not content:
        return ["unknown"]
    headings = []
    for line in content.splitlines():
        line = line.strip().lstrip("#").strip()
        if line and len(line) > 8 and not line.startswith(("!", "-", "*")):
            if line.lower() not in {point.lower() for point in headings}:
                headings.append(line)
        if len(headings) >= limit:
            break
    if headings:
        return headings[:limit]
    cleaned = normalize_whitespace(content)
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    return [sentence for sentence in sentences[:limit] if sentence] or ["unknown"]


def _infer_relevance(category: str, content: str, venture_name: str) -> str:
    haystack = f"{category} {content} {venture_name}".lower()
    if any(keyword in haystack for keyword in ["ai", "automation", "agent", "llm"]):
        return "Supports BWE's AI-native venture thesis and systems-building approach."
    if any(keyword in haystack for keyword in ["saas", "workflow", "ops", "operations"]):
        return "Supports BWE's focus on vertical SaaS and operational systems."
    if any(keyword in haystack for keyword in ["fintech", "legal", "health", "consumer", "proptech"]):
        return "Shows how BWE applies the same venture-building model across specific vertical markets."
    return "Relevant as evidence of BWE's venture-building method, even when the thesis link is indirect."


def extract_ventures() -> list[dict[str, Any]]:
    raw_ventures = load_json(VENTURES_PATH.parent.parent / "raw" / "supabase-ventures.json", [])
    ventures: list[dict[str, Any]] = []
    for venture in raw_ventures:
        name = _unknown(venture.get("name"))
        slug = venture.get("slug") or name.lower().replace(" ", "-")
        ventures.append(
            {
                "name": name,
                "description": _unknown(venture.get("description")),
                "sector": _unknown(venture.get("vertical") or venture.get("category")),
                "target_users": _unknown(venture.get("icp")),
                "problem_solved": _unknown(venture.get("problem_statement")),
                "product_type": _unknown(venture.get("category")),
                "technologies_mentioned": _list_or_unknown(venture.get("technology_stack")),
                "source_url": f"https://bwestudios.com/ventures/{slug}",
            }
        )
    save_json(VENTURES_PATH, ventures)
    return ventures


def extract_blogs() -> list[dict[str, Any]]:
    raw_blogs = load_json(BLOGS_PATH.parent.parent / "raw" / "supabase-blog-posts.json", [])
    ventures = load_json(BLOGS_PATH.parent.parent / "raw" / "supabase-ventures.json", [])
    venture_map = {venture.get("id"): venture for venture in ventures}
    blogs: list[dict[str, Any]] = []

    for post in raw_blogs:
        content = post.get("content") or ""
        excerpt = post.get("excerpt") or ""
        linked_venture = venture_map.get(post.get("primary_venture_id"), {})
        themes = []
        if post.get("category"):
            themes.append(normalize_whitespace(post["category"]))
        for tag in post.get("tags") or []:
            cleaned = normalize_whitespace(str(tag))
            if cleaned and cleaned not in themes:
                themes.append(cleaned)
        if linked_venture.get("name"):
            themes.append(linked_venture["name"])

        blogs.append(
            {
                "title": _unknown(post.get("title")),
                "url": f"https://bwestudios.com/hub/{post.get('slug')}",
                "summary": _unknown(excerpt) if excerpt else _summarize_text(content),
                "key_points": _extract_key_points(content),
                "themes": themes or ["unknown"],
                "market_or_sector_discussed": _unknown(
                    linked_venture.get("vertical") or linked_venture.get("category") or post.get("category")
                ),
                "relevance_to_bwe_thesis": _infer_relevance(
                    str(post.get("category") or ""),
                    content or excerpt,
                    str(linked_venture.get("name") or ""),
                ),
            }
        )

    save_json(BLOGS_PATH, blogs)
    return blogs


def extract_all() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ventures = extract_ventures()
    blogs = extract_blogs()
    return ventures, blogs
