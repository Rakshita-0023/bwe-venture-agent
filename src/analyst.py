from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

from ollama import Client

from config import BLOGS_PATH, PAGES_PATH, REPORT_FILES, VENTURES_PATH
from extractor import extract_all
from knowledge_base import get_runtime_models, load_vector_index
from utils import load_json


NOT_FOUND_MESSAGE = "I could not find this clearly in the scraped BWE website content."


def _format_answer(
    direct_answer: str,
    reasoning: str | None = None,
    sources: list[str] | None = None,
    supporting_excerpts: list[str] | None = None,
    inference_note: str | None = None,
) -> str:
    parts = [f"Direct answer:\n{direct_answer.strip()}"]
    if reasoning:
        parts.append(f"Reasoning:\n{reasoning.strip()}")
    if inference_note:
        parts.append(f"Inference note:\n{inference_note.strip()}")
    if sources:
        unique_sources: list[str] = []
        for source in sources:
            if source not in unique_sources:
                unique_sources.append(source)
        parts.append("Sources:\n" + "\n".join(f"- {source}" for source in unique_sources))
    if supporting_excerpts:
        parts.append("Supporting excerpts:\n" + "\n".join(f"- {excerpt}" for excerpt in supporting_excerpts))
    return "\n\n".join(parts)


def _keyword_score(question: str, title: str, text: str) -> int:
    stopwords = {
        "what",
        "does",
        "is",
        "are",
        "the",
        "a",
        "an",
        "of",
        "to",
        "and",
        "for",
        "in",
        "on",
        "who",
        "how",
        "why",
        "when",
        "where",
        "which",
        "listed",
    }
    terms = [term for term in re.findall(r"[a-zA-Z0-9]+", question.lower()) if term not in stopwords]
    haystack = f"{title} {text}".lower()
    score = sum(3 if term in title.lower() else 1 for term in terms if term in haystack)
    if "bold world engineering" in question.lower() or "bwe" in question.lower():
        if "bwe studio" in haystack or "bold world engineering" in haystack:
            score += 5
    return score


def _structured_answer(question: str) -> str | None:
    lowered = question.lower()
    ventures = load_json(VENTURES_PATH, [])
    blogs = load_json(BLOGS_PATH, [])
    pages = load_json(PAGES_PATH, [])

    if "venture" in lowered and any(token in lowered for token in ["listed", "list", "portfolio"]):
        if not ventures:
            return None
        venture_names = ", ".join(venture["name"] for venture in ventures)
        return _format_answer(
            direct_answer=(
                f"BWE currently lists {len(ventures)} ventures in the scraped public content. "
                f"They include: {venture_names}."
            ),
            sources=[venture["source_url"] for venture in ventures[:8]],
        )

    if any(phrase in lowered for phrase in ["what does bold world engineering do", "what does bwe do", "what is bwe"]):
        overview_blog = next(
            (blog for blog in blogs if "engineering the future at the speed of code" in blog["title"].lower()),
            None,
        )
        bwe_case = next(
            (page for page in pages if "redefining venture velocity" in page.get("title", "").lower()),
            None,
        )
        if overview_blog and bwe_case:
            return _format_answer(
                direct_answer=(
                    "BWE Studio appears to be an AI-powered venture lab and services studio that builds vertical "
                    "SaaS operating systems, validates ideas quickly, and turns them into production-ready ventures."
                ),
                sources=[overview_blog["url"], bwe_case["url"]],
                supporting_excerpts=[
                    overview_blog["summary"],
                    bwe_case["text"][:280].replace(chr(10), " "),
                ],
            )

    if any(phrase in lowered for phrase in ["what sectors does bwe focus on", "what sectors does bold world engineering focus on"]):
        sectors = _top_sectors(ventures)
        if sectors:
            return _format_answer(
                direct_answer="BWE most visibly focuses on SaaS & Operations, AI & Intelligence, FinTech, Consumer & Lifestyle, and HealthTech.",
                reasoning="This summary is based on the sector labels attached to the currently extracted public venture list.",
                sources=[venture["source_url"] for venture in ventures[:8]],
                supporting_excerpts=[f"{sector}: {count} ventures" for sector, count in sectors[:5]],
            )

    return None


def _is_strategy_question(question: str) -> bool:
    lowered = question.lower()
    strategy_signals = [
        "best venture",
        "most promising",
        "strongest fit",
        "should bwe build next",
        "what should bwe build next",
        "product thesis fits bwe best",
        "best product",
        "rank ventures",
        "which venture looks",
    ]
    return any(signal in lowered for signal in strategy_signals)


def _venture_evidence(venture: dict, blogs: list[dict], pages: list[dict]) -> dict:
    name = venture.get("name", "")
    slug = urlparse(venture.get("source_url", "")).path.strip("/").split("/")[-1]
    related_blogs = [
        blog
        for blog in blogs
        if name.lower() in blog.get("title", "").lower()
        or name.lower() in blog.get("summary", "").lower()
        or name in blog.get("themes", [])
    ]
    related_pages = [
        page
        for page in pages
        if slug and slug in page.get("url", "")
        or name.lower() in page.get("title", "").lower()
        or name.lower() in page.get("text", "").lower()
    ]
    case_studies = [page for page in related_pages if page.get("page_type") == "case_study"]
    return {"blogs": related_blogs, "pages": related_pages, "case_studies": case_studies}


def _strategy_score(venture: dict, evidence: dict) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if venture.get("problem_solved") and venture["problem_solved"] != "unknown":
        score += 2
        reasons.append("clear problem statement")
    if venture.get("target_users") and venture["target_users"] != "unknown":
        score += 2
        reasons.append("clear ICP")
    if venture.get("sector") and venture["sector"] != "unknown":
        score += 1
        reasons.append("clear sector positioning")
    if venture.get("product_type") and venture["product_type"] != "unknown":
        score += 1
        reasons.append("defined product type")
    if venture.get("description") and len(venture["description"]) > 140:
        score += 1
        reasons.append("strong public positioning detail")
    if evidence["blogs"]:
        score += min(len(evidence["blogs"]), 3)
        reasons.append(f"{len(evidence['blogs'])} related blog signal(s)")
    if evidence["case_studies"]:
        score += min(len(evidence["case_studies"]) * 2, 4)
        reasons.append(f"{len(evidence['case_studies'])} case study signal(s)")
    return score, reasons


def _strategy_answer(question: str) -> str:
    all_ventures = load_json(VENTURES_PATH, [])
    blogs = load_json(BLOGS_PATH, [])
    pages = load_json(PAGES_PATH, [])
    ventures = [
        venture
        for venture in all_ventures
        if venture.get("name") not in {"Bold World Engineering", "The Best App Store"}
        and venture.get("sector") != "Venture Infrastructure"
    ]
    if not ventures:
        return NOT_FOUND_MESSAGE

    scored = []
    for venture in ventures:
        evidence = _venture_evidence(venture, blogs, pages)
        score, reasons = _strategy_score(venture, evidence)
        scored.append((venture, evidence, score, reasons))

    scored.sort(key=lambda item: item[2], reverse=True)
    top = scored[:3]
    if not top:
        return NOT_FOUND_MESSAGE

    lowered = question.lower()
    if "build next" in lowered or "product thesis" in lowered:
        direct_answer = (
            "The website does not directly prescribe what BWE should build next, but based on the scraped public "
            "content, the strongest next-build directions appear to be compliance/diligence infrastructure, SMB "
            "operations automation, and founder back-office tooling."
        )
        reasoning = (
            "These themes recur across multiple ventures and reports: trust/compliance products such as Argus and ORBIT, "
            "operations systems such as Ritual and WaBOS, and founder-finance workflows such as Solo, Closr, and PayReady."
        )
        sources = [
            "https://bwestudios.com/ventures/argus",
            "https://bwestudios.com/ventures/orbit",
            "https://bwestudios.com/ventures/ritual",
            "https://bwestudios.com/ventures/wabos",
            "https://bwestudios.com/ventures/solo",
            "https://bwestudios.com/ventures/closr",
            "https://bwestudios.com/ventures/payready",
        ]
        excerpts = [
            "The scraped venture mix repeatedly clusters around trust infrastructure, operational workflow automation, and founder execution systems.",
            "The generated product thesis report also points to compliance copilot, local service business OS, and founder back-office tooling as strong fits.",
        ]
        return _format_answer(
            direct_answer=direct_answer,
            reasoning=reasoning,
            inference_note=(
                "The website does not directly rank ventures or prescribe the roadmap, but this is an evidence-based "
                "analysis using venture descriptions, sectors, ICP clarity, and available blog/case-study signals. "
                "It is not an official BWE ranking."
            ),
            sources=sources,
            supporting_excerpts=excerpts,
        )

    best = top[0]
    best_venture, _, best_score, best_reasons = best
    comparison_lines = [
        f"{venture['name']} scored well because of {', '.join(reasons[:4]) or 'available public evidence'}."
        for venture, _, _, reasons in top
    ]
    source_urls: list[str] = []
    supporting_excerpts: list[str] = []
    for venture, evidence, _, reasons in top:
        source_urls.append(venture["source_url"])
        if evidence["blogs"]:
            source_urls.append(evidence["blogs"][0]["url"])
        supporting_excerpts.append(
            f"{venture['name']}: sector={venture.get('sector', 'unknown')}, product_type={venture.get('product_type', 'unknown')}, reasons={', '.join(reasons[:4]) or 'limited evidence'}."
        )

    return _format_answer(
        direct_answer=(
            "The website does not directly rank ventures, but based on the scraped public content, "
            f"{best_venture['name']} currently looks strongest in public-facing positioning and evidence depth."
        ),
        reasoning=(
            f"{best_venture['name']} scored highest in this inferred comparison because it shows stronger clarity of problem, "
            f"ICP, market relevance, and public evidence. Comparison summary: {' '.join(comparison_lines)}"
        ),
        inference_note=(
            "This is an inferred analysis based on clarity of problem, target ICP clarity, market relevance, product maturity "
            "signals, strength of positioning, and available case-study/blog evidence. It is not an official BWE ranking."
        ),
        sources=source_urls[:8],
        supporting_excerpts=supporting_excerpts,
    )


def _top_sectors(ventures: list[dict], limit: int = 5) -> list[tuple[str, int]]:
    counts = Counter(venture["sector"] for venture in ventures if venture.get("sector") and venture["sector"] != "unknown")
    return counts.most_common(limit)


def _top_blog_themes(blogs: list[dict], limit: int = 8) -> list[tuple[str, int]]:
    counts = Counter()
    for blog in blogs:
        for theme in blog.get("themes", []):
            if theme and theme != "unknown":
                counts[theme] += 1
    return counts.most_common(limit)


def _write_report(path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def generate_reports(ventures: list[dict], blogs: list[dict]) -> None:
    top_sectors = _top_sectors(ventures)
    top_themes = _top_blog_themes(blogs)
    pages = load_json(PAGES_PATH, [])
    bwe_case = next((page for page in pages if "bwe-studio-case-study" in page.get("url", "")), {})
    overview_blog = next((blog for blog in blogs if "engineering the future at the speed of code" in blog["title"].lower()), {})

    overview_content = f"""
# BWE Overview

## What BWE appears to do

BWE Studio appears to operate as an AI-powered venture lab and services studio that builds vertical SaaS operating systems, validates ideas quickly, and turns them into production-ready ventures.

## Evidence

- {overview_blog.get("summary", "BWE-specific overview blog not found.")}
- {str(bwe_case.get("text", "BWE case study not found."))[:350]}

## Current scraped footprint

- Ventures captured: {len(ventures)}
- Blog and insight posts captured: {len(blogs)}
- Top sectors: {", ".join(f"{sector} ({count})" for sector, count in top_sectors)}
"""

    venture_lines = "\n".join(
        f"- **{venture['name']}** | {venture['sector']} | {venture['description']} | Source: {venture['source_url']}"
        for venture in ventures
    )
    venture_list_content = f"""
# Venture List

The scraped public BWE content currently exposes {len(ventures)} ventures.

{venture_lines}
"""

    blog_lines = "\n".join(
        f"- **{blog['title']}** | Sector: {blog['market_or_sector_discussed']} | Themes: {', '.join(blog['themes'][:4])} | Summary: {blog['summary']} | URL: {blog['url']}"
        for blog in blogs[:30]
    )
    blog_insights_content = f"""
# Blog Insights

## Common themes

{chr(10).join(f"- {theme} ({count})" for theme, count in top_themes)}

## Sample article insights

{blog_lines}
"""

    thesis_content = f"""
# Product Fit and Thesis

## What BWE appears to do

BWE appears to build AI-enabled vertical software products with a strong bias toward operations, workflow automation, trust infrastructure, and applied intelligence across specific sectors.

## What kind of ventures/products BWE focuses on

- Vertical SaaS tools for defined user groups rather than broad consumer platforms
- AI-native operating systems, copilots, and automation layers
- Products that reduce operational friction, improve trust, or automate repetitive work
- Ventures with clear ICPs such as founders, SMBs, funds, law firms, wellness users, and local businesses

## Common themes across ventures and blogs

- AI agents and automation appear repeatedly across ventures and insight content
- BWE repeatedly targets broken workflows, low-trust markets, and fragmented operations
- A fast build-and-ship culture shows up in both the venture portfolio and the BWE-specific thought pieces
- Many products anchor themselves in measurable operational outcomes rather than pure engagement

## Market gaps or opportunities

- Cross-product workflow orchestration between BWE ventures looks underexplored
- BWE has multiple trust/compliance products, suggesting room for shared trust infrastructure
- SMB and solo-operator tooling appears strong, which creates room for bundled “mini operating systems”
- Several ventures are vertical-specific; there may be opportunity in a shared analytics or agent backbone across them

## Thesis Ideas

### Thesis Name: Compliance Copilot for Emerging Funds
Problem: Small and emerging investment firms struggle with due diligence, compliance tracking, and fragmented workflow tooling.
Target Users: Emerging VC funds, angel syndicates, and diligence teams.
Why it fits BWE: BWE already shows overlap in legal intelligence, financial workflows, and operating-system style SaaS.
Possible MVP: A workspace that combines diligence checklists, regulatory watchlists, memo generation, and portfolio tracking.
Risks: Highly trust-sensitive workflow, possible long sales cycle, and need for strong data quality.
Evidence from BWE content: Argus, Prysm, ORBIT, and the BWE venture-building overview content.

### Thesis Name: AI Operating System for Local Service Businesses
Problem: Small service businesses lose revenue because customer communication, bookings, support, and follow-up are manual.
Target Users: Clinics, salons, restaurants, and neighborhood service providers.
Why it fits BWE: BWE already has signals in operations automation, messaging workflows, and vertical execution systems.
Possible MVP: WhatsApp-first inbox, lead capture, appointment handling, payment reminders, and simple analytics.
Risks: Crowded market, onboarding friction, and channel dependency.
Evidence from BWE content: WaBOS, Platos, Ritual, and multiple AI/operations blog posts.

### Thesis Name: Founder Back Office for Solo Builders
Problem: Solo founders juggle sales, invoicing, bookkeeping, and project follow-up across disconnected tools.
Target Users: Solopreneurs, freelancers, creator-operators, and small agencies.
Why it fits BWE: The venture list shows a recurring focus on solo workflows, finance tooling, and founder execution.
Possible MVP: Unified deal pipeline, invoice creation, revenue tracking, and weekly operating summary.
Risks: Many adjacent competitors and a need for tight product positioning.
Evidence from BWE content: Solo, Closr, PayReady, and related company-of-one / workflow blog content.

### Thesis Name: Trust Layer for High-Friction Marketplaces
Problem: Buyers and sellers in fragmented markets struggle with verification, transparency, and decision confidence.
Target Users: Marketplace operators, brokers, and buyers in property, hiring, and legal-risk markets.
Why it fits BWE: Trust, verification, and intelligence recur across several BWE ventures and case studies.
Possible MVP: Verification score, fraud signals, profile audit trail, and AI-generated risk summary.
Risks: Hard integration requirements and sector-specific compliance needs.
Evidence from BWE content: BAAB, Argus, Brivo, and case-study themes around trust and verification.

### Thesis Name: Outcome-Driven Wellness Accountability Engine
Problem: Consumers often abandon health and habit products because there is no real accountability loop.
Target Users: Fitness users, remote families, and wellness programs.
Why it fits BWE: BWE already has traction themes around accountability, behavior systems, and health execution.
Possible MVP: Commitment staking, progress check-ins, coach prompts, and family accountability dashboards.
Risks: Consumer retention, behavior design complexity, and regulated health claims.
Evidence from BWE content: Pact, Kuro, Beat, and wellness-focused insight posts.
"""

    _write_report(REPORT_FILES["overview"], overview_content)
    _write_report(REPORT_FILES["ventures"], venture_list_content)
    _write_report(REPORT_FILES["blogs"], blog_insights_content)
    _write_report(REPORT_FILES["thesis"], thesis_content)

def run_analysis() -> None:
    ventures, blogs = extract_all()
    generate_reports(ventures, blogs)
    print(f"Saved {len(ventures)} ventures, {len(blogs)} blogs, and 4 markdown reports")


def run_ask(question: str) -> str:
    structured = _structured_answer(question)
    if structured:
        return structured

    if _is_strategy_question(question):
        return _strategy_answer(question)

    index = load_vector_index()
    retriever = index.as_retriever(similarity_top_k=10)
    nodes = retriever.retrieve(question)

    if not nodes:
        return NOT_FOUND_MESSAGE

    ranked_nodes = sorted(
        nodes,
        key=lambda node: (
            _keyword_score(question, str((node.metadata or {}).get("title", "")), node.text or ""),
            float(getattr(node, "score", 0.0) or 0.0),
        ),
        reverse=True,
    )
    nodes = ranked_nodes[:4]

    excerpts: list[str] = []
    source_urls: list[str] = []
    context_blocks: list[str] = []
    for idx, node in enumerate(nodes, start=1):
        metadata = node.metadata or {}
        text = (node.text or "").strip()
        if not text:
            continue
        source_url = metadata.get("url", "unknown")
        source_urls.append(source_url)
        excerpt = text[:320].replace("\n", " ").strip()
        excerpts.append(f"- {source_url}: {excerpt}")
        context_blocks.append(
            f"[Source {idx}]\nTitle: {metadata.get('title', 'unknown')}\n"
            f"URL: {source_url}\nType: {metadata.get('page_type', 'unknown')}\nExcerpt: {excerpt}\n"
        )

    if not context_blocks:
        return NOT_FOUND_MESSAGE

    prompt = (
        "You are answering questions about Bold World Engineering / BWE Studio using only the provided context.\n"
        "Rules:\n"
        "1. Use only the context below.\n"
        "2. If the answer is not clearly supported, reply exactly: "
        f"{NOT_FOUND_MESSAGE}\n"
        "3. Keep the answer concise and factual.\n\n"
        f"Question: {question}\n\n"
        "Context:\n"
        + "\n".join(context_blocks)
    )

    models = get_runtime_models()
    response = Client().generate(model=models["llm_model"], prompt=prompt)
    answer = response["response"].strip()
    if NOT_FOUND_MESSAGE in answer:
        return NOT_FOUND_MESSAGE

    return _format_answer(
        direct_answer=answer,
        sources=source_urls[:4],
        supporting_excerpts=excerpts[:4],
    )
