from __future__ import annotations

import html
from pathlib import Path
import re

import pandas as pd
import streamlit as st

from analyst import run_ask
from config import BLOGS_PATH, PAGES_PATH, PERSONAL_ALIGNMENT_PATH, REPORT_FILES, VENTURES_PATH
from utils import load_json


st.set_page_config(page_title="BWE Venture Intelligence Agent", layout="wide")


CUSTOM_CSS = """
<style>
    :root {
        --bg: #0a0a0a;
        --bg-soft: #101010;
        --bg-elevated: #151515;
        --bg-panel: #111111;
        --border: #303030;
        --border-strong: #4a4a4a;
        --text: #ededed;
        --muted: #9a9a9a;
        --accent: #ccff00;
        --accent-soft: rgba(204, 255, 0, 0.14);
        --shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
        --radius-lg: 20px;
        --radius-md: 14px;
        --radius-sm: 10px;
        --mono: "SFMono-Regular", "Menlo", "Monaco", "Consolas", monospace;
        --sans: "Inter", "Helvetica Neue", "Arial", sans-serif;
    }

    html, body, [class*="css"] {
        font-family: var(--sans);
    }

    .stApp {
        background:
            radial-gradient(circle at top left, rgba(204, 255, 0, 0.08), transparent 22%),
            linear-gradient(180deg, #090909 0%, #0a0a0a 100%);
        color: var(--text);
    }

    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    #MainMenu,
    footer {
        visibility: hidden;
        height: 0;
        position: fixed;
    }

    .block-container {
        max-width: 1220px;
        padding-top: 0.45rem;
        padding-bottom: 3rem;
    }

    h1, h2, h3, h4, h5 {
        color: var(--text) !important;
        letter-spacing: -0.035em;
        font-weight: 700;
    }

    p, li, label, .stMarkdown, .stText, .stCaption, div {
        color: var(--text);
    }

    .hero-shell {
        position: relative;
        overflow: hidden;
        background:
            linear-gradient(180deg, rgba(21, 21, 21, 0.98), rgba(12, 12, 12, 0.98)),
            linear-gradient(90deg, rgba(204, 255, 0, 0.08), transparent);
        border: 1px solid var(--border);
        border-radius: 24px;
        padding: 1.15rem 1.2rem 1rem 1.2rem;
        box-shadow: var(--shadow);
        margin-bottom: 0.85rem;
    }

    .hero-shell:before {
        content: "";
        position: absolute;
        inset: 0;
        background:
            linear-gradient(90deg, transparent 0%, rgba(204, 255, 0, 0.03) 58%, transparent 100%);
        pointer-events: none;
    }

    .hero-grid {
        position: relative;
        z-index: 1;
        display: grid;
        grid-template-columns: 1.35fr 0.85fr;
        gap: 1rem;
        align-items: end;
    }

    .eyebrow {
        color: var(--accent);
        text-transform: uppercase;
        letter-spacing: 0.22em;
        font-size: 0.72rem;
        font-weight: 700;
        margin-bottom: 0.7rem;
        font-family: var(--mono);
    }

    .hero-title {
        font-size: clamp(2.2rem, 3.9vw, 4.2rem);
        line-height: 1.02;
        font-weight: 800;
        max-width: 740px;
        margin: 0 0 0.65rem 0;
        text-wrap: balance;
    }

    .hero-subtitle {
        color: var(--muted);
        font-size: 0.98rem;
        line-height: 1.55;
        max-width: 720px;
        margin-bottom: 0.9rem;
    }

    .pill-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
    }

    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.58rem 0.78rem;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid var(--border);
        color: var(--text);
        font-size: 0.78rem;
        font-family: var(--mono);
    }

    .status-dot {
        width: 0.5rem;
        height: 0.5rem;
        border-radius: 50%;
        background: var(--accent);
        display: inline-block;
        box-shadow: 0 0 16px rgba(204, 255, 0, 0.45);
    }

    .hero-rail {
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 0.8rem 0.9rem;
        background: rgba(255, 255, 255, 0.02);
        min-height: 100%;
    }

    .rail-label {
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-size: 0.7rem;
        font-family: var(--mono);
        margin-bottom: 0.55rem;
    }

    .rail-line {
        display: flex;
        justify-content: space-between;
        gap: 0.75rem;
        padding: 0.52rem 0;
        border-top: 1px solid rgba(255,255,255,0.05);
        font-size: 0.84rem;
    }

    .rail-line:first-of-type {
        border-top: 0;
        padding-top: 0;
    }

    .rail-key {
        color: var(--muted);
        font-family: var(--mono);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.72rem;
    }

    .rail-value {
        color: var(--text);
        text-align: right;
        font-weight: 600;
    }

    .metric-card {
        position: relative;
        background: linear-gradient(180deg, #141414 0%, #101010 100%);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 1.05rem 1rem;
        min-height: 116px;
        box-shadow: var(--shadow);
        transition: transform 180ms ease, border-color 180ms ease, background 180ms ease;
    }

    .metric-card:hover,
    .venture-card:hover,
    .blog-card:hover,
    .source-card:hover,
    .answer-card:hover,
    .section-card:hover,
    .demo-prompt:hover {
        transform: translateY(-2px);
        border-color: var(--border-strong);
    }

    .metric-label {
        color: var(--muted);
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        margin-bottom: 0.75rem;
        font-family: var(--mono);
    }

    .metric-value {
        font-size: 2rem;
        font-weight: 800;
        color: var(--text);
        margin-bottom: 0.3rem;
    }

    .metric-note {
        color: var(--muted);
        font-size: 0.84rem;
        line-height: 1.45;
    }

    .metric-index {
        position: absolute;
        top: 1rem;
        right: 1rem;
        color: rgba(204, 255, 0, 0.7);
        font-family: var(--mono);
        font-size: 0.76rem;
        letter-spacing: 0.16em;
    }

    .section-card {
        background: linear-gradient(180deg, #131313 0%, #101010 100%);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 1.15rem 1.15rem;
        box-shadow: var(--shadow);
        margin-bottom: 1rem;
        transition: transform 180ms ease, border-color 180ms ease;
    }

    .card-title {
        color: var(--text);
        font-size: 1.08rem;
        font-weight: 700;
        margin-bottom: 0.4rem;
    }

    .card-muted {
        color: var(--muted);
        font-size: 0.95rem;
        line-height: 1.68;
    }

    .memo-lead {
        font-size: 1.1rem;
        line-height: 1.72;
        color: #f3f3f3;
        margin: 0;
    }

    .memo-block {
        background: linear-gradient(180deg, #141414 0%, #101010 100%);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 1rem 1rem 0.95rem 1rem;
        margin-top: 0.85rem;
    }

    .memo-block:first-child {
        margin-top: 0;
    }

    .memo-label {
        color: var(--accent);
        font-family: var(--mono);
        text-transform: uppercase;
        letter-spacing: 0.16em;
        font-size: 0.7rem;
        margin-bottom: 0.45rem;
    }

    .memo-heading {
        font-size: 1.12rem;
        font-weight: 700;
        color: var(--text);
        margin-bottom: 0.55rem;
    }

    .memo-copy {
        color: var(--muted);
        font-size: 0.95rem;
        line-height: 1.72;
    }

    .evidence-list {
        display: grid;
        gap: 0.75rem;
        margin-top: 0.25rem;
    }

    .evidence-item {
        border-left: 2px solid rgba(204, 255, 0, 0.35);
        padding-left: 0.8rem;
        color: var(--muted);
        line-height: 1.65;
    }

    .mini-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.9rem;
        margin-top: 0.75rem;
    }

    .mini-card {
        background: rgba(255,255,255,0.02);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 0.95rem;
    }

    .mini-label {
        color: var(--muted);
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        margin-bottom: 0.35rem;
        font-family: var(--mono);
    }

    .mini-value {
        color: var(--text);
        font-size: 1.35rem;
        font-weight: 700;
    }

    .section-kicker {
        color: var(--accent);
        font-family: var(--mono);
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-size: 0.72rem;
        margin-bottom: 0.45rem;
    }

    .venture-card, .blog-card, .source-card, .answer-card {
        background: linear-gradient(180deg, #121212 0%, #0f0f0f 100%);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 1.15rem 1.15rem 1rem 1.15rem;
        margin-bottom: 0.9rem;
        box-shadow: var(--shadow);
        transition: transform 180ms ease, border-color 180ms ease, background 180ms ease;
    }

    .card-header-row {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
        margin-bottom: 0.7rem;
    }

    .card-kicker {
        color: var(--accent);
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        margin-bottom: 0.3rem;
        font-family: var(--mono);
    }

    .tag-wrap {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
        margin: 0.7rem 0 0.25rem 0;
    }

    .tag {
        display: inline-flex;
        align-items: center;
        padding: 0.34rem 0.56rem;
        border-radius: 999px;
        background: rgba(204, 255, 0, 0.06);
        color: #edf4d1;
        font-size: 0.75rem;
        border: 1px solid rgba(204, 255, 0, 0.18);
    }

    .source-link,
    .mini-link {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        margin-top: 0.9rem;
        color: var(--accent) !important;
        text-decoration: none !important;
        border: 1px solid rgba(204, 255, 0, 0.22);
        background: rgba(204, 255, 0, 0.05);
        padding: 0.58rem 0.78rem;
        border-radius: 999px;
        font-size: 0.76rem;
        font-family: var(--mono);
        transition: transform 180ms ease, background 180ms ease, border-color 180ms ease;
    }

    .source-link:hover,
    .mini-link:hover {
        transform: translateY(-1px);
        background: rgba(204, 255, 0, 0.12);
        border-color: rgba(204, 255, 0, 0.34);
    }

    .footer-note {
        margin-top: 2rem;
        border-top: 1px solid var(--border);
        padding-top: 1rem;
        color: var(--muted);
        font-size: 0.9rem;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.15rem;
        background: #111111;
        padding: 0.35rem;
        border-radius: 16px;
        border: 1px solid var(--border);
        margin-top: 0.4rem;
        box-shadow: none !important;
    }

    .stTabs [data-baseweb="tab"] {
        color: var(--muted);
        border-radius: 12px;
        padding: 0.72rem 1rem;
        font-weight: 600;
        background: transparent;
        transition: all 180ms ease;
    }

    .stTabs [aria-selected="true"] {
        background: rgba(204, 255, 0, 0.08) !important;
        color: var(--text) !important;
        border: 1px solid rgba(204, 255, 0, 0.22) !important;
    }

    .stTabs [data-baseweb="tab-highlight"] {
        background: transparent !important;
        height: 0 !important;
    }

    .stTabs [data-baseweb="tab-border"] {
        display: none !important;
    }

    .stTabs div[role="tablist"] + div {
        border-top: 0 !important;
    }

    .stTabs [data-baseweb="tab"]:hover {
        color: var(--text);
        background: rgba(255,255,255,0.025);
    }

    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
        background: #111111 !important;
        color: var(--text) !important;
        border-radius: 14px !important;
        border: 1px solid var(--border) !important;
        outline: none !important;
    }

    textarea,
    textarea:focus,
    textarea:focus-visible,
    div[data-baseweb="textarea"],
    div[data-baseweb="textarea"]:focus-within,
    .stTextArea textarea,
    .stTextArea textarea:focus,
    .stTextArea textarea:focus-visible,
    .stTextInput input,
    .stTextInput input:focus,
    .stTextInput input:focus-visible {
        outline: none !important;
    }

    .stTextArea textarea {
        min-height: 132px !important;
        font-family: var(--mono) !important;
        line-height: 1.55 !important;
        background:
            linear-gradient(180deg, rgba(17,17,17,0.98), rgba(13,13,13,0.98)) !important;
        box-shadow: inset 0 0 0 1px rgba(204, 255, 0, 0.04);
    }

    textarea:focus,
    textarea:focus-visible,
    div[data-baseweb="textarea"]:focus-within,
    .stTextArea textarea:focus,
    .stTextArea textarea:focus-visible,
    .stTextInput input:focus,
    .stTextInput input:focus-visible {
        outline: none !important;
        border-color: rgba(190, 255, 0, 0.75) !important;
        box-shadow: 0 0 0 1px rgba(190, 255, 0, 0.35), 0 0 24px rgba(190, 255, 0, 0.08) !important;
    }

    div[data-baseweb="input"]:focus-within,
    div[data-baseweb="base-input"]:focus-within,
    div[data-baseweb="textarea"]:focus-within {
        outline: none !important;
        border-color: rgba(190, 255, 0, 0.75) !important;
        box-shadow: 0 0 0 1px rgba(190, 255, 0, 0.35), 0 0 24px rgba(190, 255, 0, 0.08) !important;
    }

    .stButton button {
        border-radius: 999px;
        border: 1px solid rgba(204, 255, 0, 0.22);
        background: rgba(204, 255, 0, 0.06);
        color: var(--text);
        font-weight: 600;
        transition: all 180ms ease;
        min-height: 2.9rem;
    }

    .stButton button:hover {
        border-color: rgba(204, 255, 0, 0.38);
        background: rgba(204, 255, 0, 0.12);
        color: var(--text);
    }

    .stButton button[kind="secondary"] {
        border-radius: 16px;
        min-height: 108px;
        width: 100%;
        justify-content: flex-start !important;
        align-items: flex-start !important;
        text-align: left !important;
        padding: 0.95rem !important;
        background: linear-gradient(180deg, #131313 0%, #101010 100%);
        border: 1px solid var(--border);
        white-space: normal !important;
    }

    .stButton button[kind="secondary"] p {
        white-space: pre-wrap !important;
        line-height: 1.45 !important;
        font-family: var(--sans) !important;
        font-size: 0.98rem !important;
        text-align: left !important;
    }

    .stButton button[kind="primary"] {
        background: linear-gradient(180deg, rgba(204,255,0,0.2), rgba(204,255,0,0.1));
        border-color: rgba(204,255,0,0.4);
        color: #f3ffd0;
        box-shadow: 0 0 0 1px rgba(204,255,0,0.08), 0 0 26px rgba(204,255,0,0.08);
    }

    .stExpander {
        border: 1px solid var(--border) !important;
        border-radius: 14px !important;
        background: rgba(255,255,255,0.02) !important;
    }

    .stDataFrame {
        border: 1px solid var(--border);
        border-radius: 14px;
        overflow: hidden;
    }

    .demo-prompt {
        background: linear-gradient(180deg, #131313 0%, #101010 100%);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 0.95rem;
        min-height: 112px;
        margin-bottom: 0.75rem;
        transition: transform 180ms ease, border-color 180ms ease;
    }

    .demo-prompt-title {
        font-size: 0.78rem;
        color: var(--muted);
        font-family: var(--mono);
        text-transform: uppercase;
        letter-spacing: 0.14em;
        margin-bottom: 0.48rem;
    }

    .demo-prompt-text {
        font-size: 1rem;
        line-height: 1.45;
        color: var(--text);
    }

    .console-shell {
        background: linear-gradient(180deg, #121212 0%, #0f0f0f 100%);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 1rem;
        margin-bottom: 1rem;
    }

    .note-strip {
        border-left: 2px solid var(--accent);
        padding: 0.7rem 0 0.7rem 0.9rem;
        color: var(--muted);
        margin-top: 0.5rem;
    }

    .report-note {
        border: 1px solid rgba(204, 255, 0, 0.18);
        background: rgba(204, 255, 0, 0.04);
        border-radius: 14px;
        padding: 0.85rem 0.95rem;
        color: #d8e6a1;
        margin-bottom: 1rem;
    }

    @media (max-width: 900px) {
        .hero-grid {
            grid-template-columns: 1fr;
        }
        .mini-grid {
            grid-template-columns: 1fr;
        }
        .hero-shell {
            padding: 1rem;
        }
    }
</style>
"""


st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


@st.cache_data
def _load_ventures() -> list[dict]:
    return load_json(VENTURES_PATH, [])


@st.cache_data
def _load_blogs() -> list[dict]:
    return load_json(BLOGS_PATH, [])


@st.cache_data
def _load_pages() -> list[dict]:
    return load_json(PAGES_PATH, [])


@st.cache_data
def _load_report(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else "Report not generated yet."


@st.cache_data
def _load_alignment() -> list[dict]:
    return load_json(PERSONAL_ALIGNMENT_PATH, [])


@st.cache_data
def _cached_agent_answer(question: str, voice: str = "normal") -> str:
    return run_ask(question, voice=voice)


def _html_metric_card(index: str, label: str, value: str, note: str) -> str:
    return f"""
    <div class="metric-card">
        <div class="metric-index">{index}</div>
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-note">{note}</div>
    </div>
    """


def _section_header(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="section-card">
            <div class="section-kicker">{html.escape(kicker)}</div>
            <div class="card-title">{title}</div>
            <div class="card-muted">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _safe_value(value: object) -> str:
    if value in (None, "", [], {}):
        return "unknown"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "unknown"
    return str(value)


def _parse_answer_sections(answer: str) -> dict[str, object]:
    sections: dict[str, object] = {}
    current_key: str | None = None
    lines: list[str] = []
    headings = {
        "Direct answer:": "direct_answer",
        "Reasoning:": "reasoning",
        "Inference note:": "inference_note",
        "Sources:": "sources",
        "Supporting excerpts:": "supporting_excerpts",
    }
    for raw_line in answer.splitlines():
        line = raw_line.rstrip()
        if line in headings:
            if current_key is not None:
                sections[current_key] = "\n".join(lines).strip()
            current_key = headings[line]
            lines = []
        else:
            lines.append(line)
    if current_key is not None:
        sections[current_key] = "\n".join(lines).strip()

    for key in ["sources", "supporting_excerpts"]:
        value = sections.get(key, "")
        if isinstance(value, str) and value:
            sections[key] = [item[2:].strip() for item in value.splitlines() if item.strip().startswith("- ")]
        else:
            sections[key] = []
    return sections


def _render_answer(answer: str) -> None:
    parsed = _parse_answer_sections(answer)
    direct_answer = parsed.get("direct_answer")
    if not direct_answer:
        st.markdown(f'<div class="answer-card">{html.escape(answer)}</div>', unsafe_allow_html=True)
        return

    st.markdown(
        f"""
        <div class="answer-card">
            <div class="card-kicker">Agent Answer</div>
            <div class="card-title">Direct Answer</div>
            <div class="card-muted">{html.escape(str(direct_answer))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if parsed.get("reasoning"):
        st.markdown(
            f"""
            <div class="section-card">
                <div class="section-kicker">Reasoning</div>
                <div class="card-title">Reasoning</div>
                <div class="card-muted">{html.escape(str(parsed['reasoning']))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if parsed.get("inference_note"):
        st.markdown(
            f"""
            <div class="report-note">
                {html.escape(str(parsed['inference_note']))}
            </div>
            """,
            unsafe_allow_html=True,
        )

    sources = parsed.get("sources", [])
    if sources:
        st.markdown("#### Sources")
        cols = st.columns(2)
        for idx, source in enumerate(sources):
            with cols[idx % 2]:
                safe_source = html.escape(str(source))
                st.markdown(
                    f"""
                    <div class="source-card">
                        <div class="card-kicker">Source {idx + 1}</div>
                        <div class="card-muted"><a href="{safe_source}" target="_blank">{safe_source}</a></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    excerpts = parsed.get("supporting_excerpts", [])
    if excerpts:
        st.markdown("#### Supporting Excerpts")
        for idx, excerpt in enumerate(excerpts, start=1):
            with st.expander(f"Excerpt {idx}"):
                st.write(excerpt)


def _venture_matches_filters(venture: dict, query: str, sector_filter: str, product_filter: str) -> bool:
    haystack = " ".join(
        [
            _safe_value(venture.get("name")),
            _safe_value(venture.get("description")),
            _safe_value(venture.get("problem_solved")),
        ]
    ).lower()
    query_ok = not query or query.lower() in haystack
    sector_ok = sector_filter == "All" or _safe_value(venture.get("sector")) == sector_filter
    product_ok = product_filter == "All" or _safe_value(venture.get("product_type")) == product_filter
    return query_ok and sector_ok and product_ok


def _blog_matches_filters(blog: dict, query: str, sector_filter: str) -> bool:
    haystack = " ".join(
        [
            _safe_value(blog.get("title")),
            _safe_value(blog.get("summary")),
            _safe_value(blog.get("market_or_sector_discussed")),
        ]
    ).lower()
    query_ok = not query or query.lower() in haystack
    sector_ok = sector_filter == "All" or _safe_value(blog.get("market_or_sector_discussed")) == sector_filter
    return query_ok and sector_ok


def _html_link(url: str, label: str = "Open Source") -> str:
    if url in {"", "unknown"}:
        return ""
    safe_url = html.escape(url)
    safe_label = html.escape(label)
    return f'<a class="source-link" href="{safe_url}" target="_blank">{safe_label}</a>'


def _parse_report_sections(report_text: str) -> list[tuple[str, str]]:
    cleaned = report_text.strip()
    if not cleaned:
        return []
    cleaned = re.sub(r"^# .+\n+", "", cleaned, count=1)
    matches = list(re.finditer(r"^##\s+(.+)$", cleaned, flags=re.MULTILINE))
    if not matches:
        return []

    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        body = cleaned[start:end].strip()
        sections.append((title, body))
    return sections


def _render_overview_memo(report_text: str) -> None:
    sections = _parse_report_sections(report_text)
    if not sections:
        st.markdown(report_text)
        return

    main_section = next((body for title, body in sections if "appears to do" in title.lower()), "")
    evidence_body = next((body for title, body in sections if title.lower() == "evidence"), "")

    st.markdown(
        """
        <div class="memo-block">
            <div class="memo-label">BWE Brief</div>
            <div class="memo-heading">What BWE appears to do</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(f'<p class="memo-lead">{html.escape(main_section.strip())}</p>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if evidence_body:
        bullets = []
        for raw_line in evidence_body.splitlines():
            line = raw_line.strip()
            if line.startswith("- "):
                bullets.append(line[2:].strip())

        st.markdown(
            """
            <div class="memo-block">
                <div class="memo-label">Public Evidence</div>
                <div class="memo-heading">Why this reading is supported by the site</div>
                <div class="evidence-list">
            """,
            unsafe_allow_html=True,
        )
        for bullet in bullets:
            st.markdown(f'<div class="evidence-item">{html.escape(bullet)}</div>', unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)


def _render_alignment_card(item: dict) -> None:
    st.markdown(
        f"""
        <div class="venture-card">
            <div class="card-header-row">
                <div>
                    <div class="card-kicker">Rank #{html.escape(str(item.get('rank', 'unknown')))} · {html.escape(_safe_value(item.get('sector')))}</div>
                    <div class="card-title">{html.escape(_safe_value(item.get('venture_name')))}</div>
                </div>
                <div class="tag">{html.escape(str(item.get('alignment_score', 'unknown')))} / 40</div>
            </div>
            <div class="card-muted">{html.escape(_safe_value(item.get('why_it_aligns_with_me')))}</div>
            <div class="tag-wrap">
                <span class="tag">Skills: {html.escape(", ".join(item.get('skills_i_can_apply', [])[:4]) or 'unknown')}</span>
                <span class="tag">Learn: {html.escape(", ".join(item.get('what_i_can_learn', [])[:3]) or 'unknown')}</span>
            </div>
            {_html_link(_safe_value(item.get('source_url')), 'Open Venture Source')}
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander(f"Open personal fit brief: {_safe_value(item.get('venture_name'))}"):
        st.write(f"Alignment score: {_safe_value(item.get('alignment_score'))}/40 ({_safe_value(item.get('alignment_score_average'))}/5)")
        st.write(f"Why it fits me: {_safe_value(item.get('why_it_aligns_with_me'))}")
        st.write(f"Skills I can apply: {', '.join(item.get('skills_i_can_apply', [])) or 'unknown'}")
        st.write(f"What I can learn: {', '.join(item.get('what_i_can_learn', [])) or 'unknown'}")
        st.write(f"Possible contribution ideas: {', '.join(item.get('possible_contribution_ideas', [])) or 'unknown'}")
        st.write(f"Risks / Unknowns: {', '.join(item.get('risks_or_unknowns', [])) or 'unknown'}")
        st.write(f"Evidence from BWE content: {_safe_value(item.get('evidence_from_bwe_content'))}")


def main() -> None:
    ventures = _load_ventures()
    blogs = _load_blogs()
    pages = _load_pages()
    alignment = _load_alignment()

    case_study_count = sum(1 for page in pages if page.get("page_type") == "case_study")
    report_count = len(REPORT_FILES)

    if "ask_question" not in st.session_state:
        st.session_state.ask_question = ""
    if "last_answer" not in st.session_state:
        st.session_state.last_answer = ""
    if "voice_question" not in st.session_state:
        st.session_state.voice_question = "What product thesis fits BWE best?"
    if "voice_answer" not in st.session_state:
        st.session_state.voice_answer = ""

    st.markdown(
        """
        <div class="hero-shell">
            <div class="hero-grid">
                <div>
                    <div class="eyebrow">VENTURE INTELLIGENCE AGENT</div>
                    <div class="hero-title">BWE Venture Intelligence Agent</div>
                    <div class="hero-subtitle">
                        A local-first intelligence layer for BWE ventures, blogs, case studies, product-fit, and thesis discovery.
                    </div>
                    <div class="pill-row">
                        <div class="status-pill"><span class="status-dot"></span>Local LLM: llama3.1</div>
                        <div class="status-pill"><span class="status-dot"></span>Embeddings: nomic-embed-text</div>
                        <div class="status-pill"><span class="status-dot"></span>Vector DB: ChromaDB</div>
                        <div class="status-pill"><span class="status-dot"></span>Source: Public BWE/BWE Studio content</div>
                    </div>
                </div>
                <div class="hero-rail">
                    <div class="rail-label">Internal Briefing Surface</div>
                    <div class="rail-line">
                        <div class="rail-key">Mode</div>
                        <div class="rail-value">Local-first research</div>
                    </div>
                    <div class="rail-line">
                        <div class="rail-key">Grounding</div>
                        <div class="rail-value">Public BWE website content</div>
                    </div>
                    <div class="rail-line">
                        <div class="rail-key">Outputs</div>
                        <div class="rail-value">Research, QA, thesis, product fit</div>
                    </div>
                    <div class="rail-line">
                        <div class="rail-key">Demo Use</div>
                        <div class="rail-value">Internal venture intelligence memo</div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(_html_metric_card("01", "Ventures", str(len(ventures)), "Structured venture records extracted from public BWE content."), unsafe_allow_html=True)
    with m2:
        st.markdown(_html_metric_card("02", "Blogs / Insights", str(len(blogs)), "Blog and intelligence posts available for strategy analysis."), unsafe_allow_html=True)
    with m3:
        st.markdown(_html_metric_card("03", "Case Studies", str(case_study_count), "Public case-study evidence captured across the portfolio."), unsafe_allow_html=True)
    with m4:
        st.markdown(_html_metric_card("04", "Strategy Reports", str(report_count), "Overview, venture list, blog intelligence, and product thesis outputs."), unsafe_allow_html=True)

    overview_tab, ventures_tab, blogs_tab, ask_tab, fit_tab, thesis_tab, voice_tab = st.tabs(
        ["Overview", "Ventures", "Blog Intelligence", "Ask Agent", "My Venture Fit", "Product Thesis", "BWE Voice Mode"]
    )

    with overview_tab:
        _section_header(
            "Overview",
            "Executive Overview",
            "A concise internal briefing on what BWE appears to do, what the public portfolio signals, and why this local intelligence layer matters.",
        )
        c1, c2 = st.columns([1.15, 1])
        with c1:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            _render_overview_memo(_load_report(REPORT_FILES["overview"]))
            st.markdown("</div>", unsafe_allow_html=True)
        with c2:
            st.markdown(
                f"""
                <div class="section-card">
                    <div class="section-kicker">Scraped Footprint</div>
                    <div class="card-title">Current Scraped Footprint</div>
                    <div class="mini-grid">
                        <div class="mini-card">
                            <div class="mini-label">Ventures</div>
                            <div class="mini-value">{len(ventures)}</div>
                        </div>
                        <div class="mini-card">
                            <div class="mini-label">Blogs / Insights</div>
                            <div class="mini-value">{len(blogs)}</div>
                        </div>
                        <div class="mini-card">
                            <div class="mini-label">Case Studies</div>
                            <div class="mini-value">{case_study_count}</div>
                        </div>
                        <div class="mini-card">
                            <div class="mini-label">Reports</div>
                            <div class="mini-value">{report_count}</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <div class="section-card">
                    <div class="section-kicker">Agent Scope</div>
                    <div class="card-title">What this agent does</div>
                    <div class="card-muted">
                        • Crawls BWE public content<br>
                        • Extracts ventures and blogs<br>
                        • Builds local knowledge base<br>
                        • Answers grounded questions<br>
                        • Generates thesis reports
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <div class="section-card">
                    <div class="section-kicker">Why It Matters</div>
                    <div class="card-title">Why this matters</div>
                    <div class="card-muted">
                        It turns scattered public portfolio and insight content into a local internal research surface:
                        faster venture review, faster hypothesis generation, and clearer thesis discovery without using paid APIs.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with ventures_tab:
        _section_header(
            "Ventures",
            "Venture Portfolio Explorer",
            "Search, filter, and inspect the venture set through BWE-style intelligence cards instead of a raw spreadsheet-first view.",
        )
        sector_options = ["All"] + sorted({_safe_value(venture.get("sector")) for venture in ventures})
        product_options = ["All"] + sorted({_safe_value(venture.get("product_type")) for venture in ventures})
        q1, q2, q3 = st.columns([1.4, 1, 1])
        venture_query = q1.text_input("Search ventures", placeholder="Search by venture name or problem")
        venture_sector = q2.selectbox("Filter by sector", sector_options)
        venture_product = q3.selectbox("Filter by product type", product_options)

        filtered_ventures = [
            venture
            for venture in ventures
            if _venture_matches_filters(venture, venture_query, venture_sector, venture_product)
        ]

        st.caption(f"Showing {len(filtered_ventures)} of {len(ventures)} ventures.")
        for venture in filtered_ventures[:24]:
            venture_name = _safe_value(venture.get("name"))
            venture_sector = _safe_value(venture.get("sector"))
            venture_product = _safe_value(venture.get("product_type"))
            venture_description = _safe_value(venture.get("description"))
            venture_problem = _safe_value(venture.get("problem_solved"))
            venture_target = _safe_value(venture.get("target_users"))
            source_url = _safe_value(venture.get("source_url"))
            st.markdown(
                f"""
                <div class="venture-card">
                    <div class="card-header-row">
                        <div>
                            <div class="card-kicker">{html.escape(venture_sector)}</div>
                            <div class="card-title">{html.escape(venture_name)}</div>
                        </div>
                        <div class="tag">{html.escape(venture_product)}</div>
                    </div>
                    <div class="card-muted">{html.escape(venture_description)}</div>
                    <div class="tag-wrap">
                        <span class="tag">ICP: {html.escape(venture_target[:88])}</span>
                        <span class="tag">Problem: {html.escape(venture_problem[:88])}</span>
                    </div>
                    {_html_link(source_url, "Open Venture Source")}
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander(f"Open venture brief: {venture_name}"):
                st.write(f"Sector: {venture_sector}")
                st.write(f"Product type: {venture_product}")
                st.write(f"Problem solved: {venture_problem}")
                st.write(f"Target users: {venture_target}")
                st.write(f"Technologies mentioned: {_safe_value(venture.get('technologies_mentioned'))}")
                st.markdown(f"Source URL: <{source_url}>")

        with st.expander("Raw Venture Dataset"):
            venture_df = pd.DataFrame(filtered_ventures)
            st.dataframe(venture_df, width="stretch", hide_index=True)

    with blogs_tab:
        _section_header(
            "Blog Intelligence",
            "Blog Intelligence",
            "Use the public blog and insight archive as a content-intelligence layer for market themes, sectors, and portfolio narrative signals.",
        )
        blog_sector_options = ["All"] + sorted({_safe_value(blog.get("market_or_sector_discussed")) for blog in blogs})
        b1, b2 = st.columns([1.5, 1])
        blog_query = b1.text_input("Search blog title or summary", placeholder="Search insights, sectors, or titles")
        blog_sector = b2.selectbox("Filter by market / sector", blog_sector_options)

        filtered_blogs = [blog for blog in blogs if _blog_matches_filters(blog, blog_query, blog_sector)]
        st.caption(f"Showing {len(filtered_blogs)} of {len(blogs)} blog and insight records.")

        for blog in filtered_blogs[:20]:
            blog_title = _safe_value(blog.get("title"))
            blog_sector_value = _safe_value(blog.get("market_or_sector_discussed"))
            blog_summary = _safe_value(blog.get("summary"))
            blog_url = _safe_value(blog.get("url"))
            st.markdown(
                f"""
                <div class="blog-card">
                    <div class="card-kicker">{html.escape(blog_sector_value)}</div>
                    <div class="card-title">{html.escape(blog_title)}</div>
                    <div class="card-muted">{html.escape(blog_summary)}</div>
                    <div class="tag-wrap">
                        {''.join(f'<span class="tag">{html.escape(str(theme))}</span>' for theme in blog.get('themes', [])[:5])}
                    </div>
                    {_html_link(blog_url, "Open Insight Source")}
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander(f"Open blog intelligence: {blog_title}"):
                st.write(f"Sector: {blog_sector_value}")
                st.write(f"Relevance to BWE thesis: {_safe_value(blog.get('relevance_to_bwe_thesis'))}")
                st.write(f"Key points: {_safe_value(blog.get('key_points'))}")
                st.markdown(f"URL: <{blog_url}>")

        with st.expander("Raw Blog Dataset"):
            blog_df = pd.DataFrame(filtered_blogs)
            st.dataframe(blog_df, width="stretch", hide_index=True)

    with ask_tab:
        _section_header(
            "Ask Agent",
            "Ask the BWE Agent",
            "The main demo surface: grounded factual answers when the site states them, and evidence-based strategic comparisons when the site only implies them.",
        )

        demo_questions = [
            "What does Bold World Engineering do?",
            "What ventures are listed?",
            "Which venture looks most promising based on available content?",
            "What product thesis fits BWE best?",
            "What sectors does BWE focus on?",
            "What should BWE build next?",
        ]

        st.markdown(
            """
            <div class="section-card">
                <div class="section-kicker">Demo Questions</div>
                <div class="card-title">Try a question that shows both grounding and inference</div>
                <div class="card-muted">
                    Factual prompts answer only from scraped content. Strategy prompts stay evidence-based and clearly marked as inferred analysis rather than official BWE rankings.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        demo_cols = st.columns(3)
        for idx, question in enumerate(demo_questions):
            with demo_cols[idx % 3]:
                if st.button(
                    f"Prompt {idx + 1:02d}\n{question}",
                    key=f"demo_q_{idx}",
                    width="stretch",
                ):
                    st.session_state.ask_question = question

        question = st.text_area(
            "Question",
            key="ask_question",
            placeholder="Ask about ventures, sectors, product fit, rankings, or what BWE should build next...",
            height=132,
        )
        st.markdown(
            """
            <div class="note-strip">
                Subjective prompts are labeled as evidence-based inference, not official BWE ranking.
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Ask BWE Agent", type="primary", width="content"):
            if not question.strip():
                st.warning("Enter a question first.")
            else:
                with st.spinner("Querying local knowledge base and venture evidence..."):
                    st.session_state.last_answer = run_ask(question)

        if st.session_state.last_answer:
            _render_answer(st.session_state.last_answer)

    with fit_tab:
        _section_header(
            "My Venture Fit",
            "Personal Venture Alignment",
            "A personal-fit layer built from your profile and the extracted BWE venture set. This is a personal alignment analysis, not an official BWE ranking.",
        )
        if not alignment:
            st.markdown(
                """
                <div class="section-card">
                    <div class="section-kicker">Alignment Missing</div>
                    <div class="card-title">Run the alignment report first</div>
                    <div class="card-muted">Generate `data/reports/personal_venture_alignment.md` and `data/processed/personal_alignment.json` with `python src/cli.py align`.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            top_alignment = alignment[:5]
            st.markdown(
                """
                <div class="report-note">
                    This tab reflects a personal-fit analysis grounded in the extracted venture data. It is meant to surface where your AI, full-stack, product, and automation skill set can be most useful.
                </div>
                """,
                unsafe_allow_html=True,
            )
            for item in top_alignment:
                _render_alignment_card(item)

            with st.expander("Full alignment dataset"):
                st.dataframe(pd.DataFrame(alignment), width="stretch", hide_index=True)

    with thesis_tab:
        _section_header(
            "Product Thesis",
            "Product Fit and Thesis Report",
            "Generated from scraped ventures, blogs, and case studies.",
        )
        st.markdown(
            """
            <div class="report-note">
                Generated from scraped ventures, blogs, and case-study content.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown(_load_report(REPORT_FILES["thesis"]))
        st.markdown("</div>", unsafe_allow_html=True)

    with voice_tab:
        _section_header(
            "BWE Voice Mode",
            "BWE Voice / Style Extraction",
            "See the extracted writing patterns, compare a normal answer to a BWE-style answer, and ask grounded questions in BWE voice mode.",
        )
        st.markdown(
            """
            <div class="report-note">
                BWE voice mode keeps claims grounded in scraped content, then rewrites the answer in a sharper venture-studio style using the local style guide.
                <br><br>
                This is not model weight fine-tuning. This is a local style-adaptation layer based on extracted BWE writing patterns.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown(_load_report(REPORT_FILES["style_guide"]))
        st.markdown("</div>", unsafe_allow_html=True)

        example_question = "What product thesis fits BWE best?"
        left, right = st.columns(2)
        with left:
            st.markdown("#### Example Normal Answer")
            st.caption("Plain grounded answer: factual, direct, and source-led.")
            _render_answer(_cached_agent_answer(example_question, "normal"))
        with right:
            st.markdown("#### Example BWE-style Answer")
            st.caption("Sharper BWE-inspired answer: thesis-led, market-friction-first, and still grounded in the same evidence.")
            _render_answer(_cached_agent_answer(example_question, "bwe"))

        st.markdown("#### Ask in BWE-style mode")
        voice_question = st.text_area(
            "BWE-style question",
            key="voice_question",
            placeholder="Ask for a grounded answer in BWE-aligned strategic voice...",
            height=132,
        )
        if st.button("Ask in BWE Voice", type="primary", key="voice_mode_button", width="content"):
            if not voice_question.strip():
                st.warning("Enter a question first.")
            else:
                with st.spinner("Generating grounded answer in BWE voice mode..."):
                    st.session_state.voice_answer = run_ask(voice_question, voice="bwe")

        if st.session_state.voice_answer:
            _render_answer(st.session_state.voice_answer)

    st.markdown(
        """
        <div class="footer-note">
            Built as a local-first BWE Venture Intelligence Agent. Runs with Ollama, ChromaDB, and public BWE/BWE Studio content.
            <br><br>
            Local LLM: llama3.1 &nbsp;|&nbsp; Embeddings: nomic-embed-text &nbsp;|&nbsp; Vector DB: ChromaDB &nbsp;|&nbsp; Data source: Public BWE/BWE Studio website content
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
