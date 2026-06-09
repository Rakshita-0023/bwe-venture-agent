from __future__ import annotations

import re
from collections import Counter
from statistics import mean
from urllib.parse import urlparse

from ollama import Client

from config import (
    BLOGS_PATH,
    PAGES_PATH,
    PERSONAL_ALIGNMENT_PATH,
    PERSONAL_PROFILE_PATH,
    REPORT_FILES,
    VENTURES_PATH,
)
from extractor import extract_all
from knowledge_base import get_runtime_models, load_vector_index
from style_analyzer import load_style_guide_text, rewrite_sections_in_bwe_voice
from utils import load_json, save_json


NOT_FOUND_MESSAGE = "I could not find this clearly in the scraped BWE website content."
PERSONAL_ALIGNMENT_NOTE = (
    "This is a personal alignment analysis based on the provided technical profile. "
    "It is not an official BWE ranking."
)


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


def _apply_voice(answer: str, question: str, voice: str = "normal") -> str:
    if voice != "bwe" or answer == NOT_FOUND_MESSAGE:
        return answer

    sections = _parse_answer_sections(answer)
    direct_answer = str(sections.get("direct_answer") or "").strip()
    if not direct_answer:
        return answer

    rewritten = rewrite_sections_in_bwe_voice(
        question=question,
        direct_answer=direct_answer,
        reasoning=str(sections.get("reasoning") or "").strip() or None,
        inference_note=str(sections.get("inference_note") or "").strip() or None,
    )
    return _format_answer(
        direct_answer=rewritten["direct_answer"],
        reasoning=rewritten.get("reasoning") or None,
        inference_note=rewritten.get("inference_note") or None,
        sources=list(sections.get("sources", [])),
        supporting_excerpts=list(sections.get("supporting_excerpts", [])),
    )


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
        "with",
        "me",
        "most",
    }
    terms = [term for term in re.findall(r"[a-zA-Z0-9]+", question.lower()) if term not in stopwords]
    haystack = f"{title} {text}".lower()
    score = sum(3 if term in title.lower() else 1 for term in terms if term in haystack)
    if "bold world engineering" in question.lower() or "bwe" in question.lower():
        if "bwe studio" in haystack or "bold world engineering" in haystack:
            score += 5
    return score


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
        if (slug and slug in page.get("url", ""))
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


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _score_by_keywords(text: str, strong: list[str], medium: list[str], base: int = 2) -> int:
    lowered = text.lower()
    strong_hits = sum(1 for keyword in strong if keyword in lowered)
    medium_hits = sum(1 for keyword in medium if keyword in lowered)
    score = base + min(2, strong_hits) + (1 if medium_hits >= 2 else 0)
    return max(1, min(5, score))


def _load_personal_profile() -> str:
    if PERSONAL_PROFILE_PATH.exists():
        return PERSONAL_PROFILE_PATH.read_text(encoding="utf-8").strip()
    return ""


def _suggest_applicable_skills(venture_text: str) -> list[str]:
    skills: list[str] = []
    lowered = venture_text.lower()
    if _contains_any(lowered, ["ai", "agent", "intelligence", "copilot", "scribe", "automation"]):
        skills.extend(["Python", "LangGraph", "RAG systems", "local AI tools", "API integrations"])
    if _contains_any(lowered, ["platform", "saas", "dashboard", "workspace", "operating system", "workflow", "ops"]):
        skills.extend(["React", "Next.js", "FastAPI", "Node.js", "PostgreSQL"])
    if _contains_any(lowered, ["integration", "pipeline", "real-time", "inbox", "notifications", "management"]):
        skills.extend(["Docker", "backend APIs", "real-time workflows", "product dashboards"])
    if not skills:
        skills.extend(["Python", "React", "FastAPI", "product prototyping"])
    ordered: list[str] = []
    for skill in skills:
        if skill not in ordered:
            ordered.append(skill)
    return ordered[:6]


def _suggest_learning_areas(venture: dict) -> list[str]:
    sector = str(venture.get("sector", "unknown"))
    product_type = str(venture.get("product_type", "unknown"))
    learning: list[str] = []
    if sector == "LegalTech":
        learning.extend(["legal diligence workflows", "regulatory data sources", "evidence-backed audit trails"])
    if sector == "FinTech":
        learning.extend(["payment/compliance primitives", "financial workflow ops", "trust-sensitive product design"])
    if sector == "HealthTech":
        learning.extend(["clinical workflow constraints", "health-data UX", "safety-sensitive automation"])
    if _contains_any(product_type.lower(), ["saas", "operations", "workflow", "platform"]):
        learning.extend(["vertical SaaS positioning", "operational workflow design"])
    if _contains_any(str(venture.get("description", "")).lower(), ["ai", "automation", "intelligence", "copilot"]):
        learning.extend(["AI product evaluation", "agent reliability", "human-in-the-loop workflow design"])
    if not learning:
        learning.extend(["venture discovery", "ICP validation", "fast product iteration"])
    ordered: list[str] = []
    for item in learning:
        if item not in ordered:
            ordered.append(item)
    return ordered[:4]


def _possible_contribution_ideas(venture: dict, venture_text: str) -> list[str]:
    ideas: list[str] = []
    name = venture.get("name", "This venture")
    if _contains_any(venture_text, ["ai", "agent", "automation", "intelligence", "copilot"]):
        ideas.append(f"Prototype an AI workflow or copilot surface that sharpens the core {name} execution loop.")
    if _contains_any(venture_text, ["platform", "saas", "dashboard", "workspace", "management", "ops", "workflow"]):
        ideas.append(f"Build or refine internal dashboards, APIs, and operator tooling that make {name} easier to ship and test.")
    if _contains_any(venture_text, ["compliance", "trust", "due diligence", "verification", "property", "payments"]):
        ideas.append(f"Create evidence pipelines, reporting views, or trust-layer UX that make {name} more explainable and production-ready.")
    if not ideas:
        ideas.append(f"Ship fast product experiments and instrumentation loops to validate how {name} creates value for its ICP.")
    ideas.append(f"Turn scraped market or user evidence into tighter product requirements and iteration ideas for {name}.")
    ordered: list[str] = []
    for item in ideas:
        if item not in ordered:
            ordered.append(item)
    return ordered[:3]


def _alignment_evidence_text(venture: dict, evidence: dict) -> str:
    evidence_parts = [
        f"Problem: {venture.get('problem_solved', 'unknown')}",
        f"ICP: {venture.get('target_users', 'unknown')}",
        f"Public evidence count: {len(evidence['blogs'])} blogs, {len(evidence['case_studies'])} case studies, {len(evidence['pages'])} related pages",
    ]
    return " | ".join(evidence_parts)


def _score_alignment(venture: dict, evidence: dict) -> dict:
    venture_text = " ".join(
        [
            str(venture.get("name", "")),
            str(venture.get("description", "")),
            str(venture.get("sector", "")),
            str(venture.get("target_users", "")),
            str(venture.get("problem_solved", "")),
            str(venture.get("product_type", "")),
            str(venture.get("technologies_mentioned", "")),
            " ".join(blog.get("summary", "") for blog in evidence["blogs"][:3]),
        ]
    ).lower()

    ai_relevance = _score_by_keywords(
        venture_text,
        ["ai", "agent", "copilot", "intelligence", "ambient", "automation", "embeddings"],
        ["search", "assistant", "model", "data", "workflow"],
    )
    full_stack_relevance = _score_by_keywords(
        venture_text,
        ["platform", "saas", "dashboard", "workspace", "app", "api", "operating system"],
        ["management", "system", "tooling", "product", "portal"],
    )
    automation_relevance = _score_by_keywords(
        venture_text,
        ["automation", "workflow", "ops", "operating system", "execution", "pipeline"],
        ["management", "back office", "notifications", "routing", "coordination"],
    )
    learning_opportunity = min(
        5,
        2
        + (1 if venture.get("technologies_mentioned") != "unknown" else 0)
        + (1 if venture.get("sector") in {"LegalTech", "FinTech", "HealthTech", "AI & Intelligence"} else 0)
        + (1 if evidence["case_studies"] else 0),
    )
    product_building_relevance = min(
        5,
        2
        + (1 if venture.get("problem_solved") != "unknown" else 0)
        + (1 if venture.get("target_users") != "unknown" else 0)
        + (1 if venture.get("product_type") != "unknown" else 0),
    )
    personal_interest_fit = max(1, min(5, round(mean([ai_relevance, full_stack_relevance, automation_relevance, product_building_relevance]))))
    clarity_problem_icp = min(
        5,
        1
        + (2 if venture.get("problem_solved") not in {"unknown", ""} else 0)
        + (1 if venture.get("target_users") not in {"unknown", ""} else 0)
        + (1 if len(str(venture.get("description", ""))) > 140 else 0),
    )
    evidence_available = min(5, 1 + min(4, len(evidence["blogs"]) + len(evidence["case_studies"]) + (1 if evidence["pages"] else 0)))

    criteria_scores = {
        "ai_agentic_workflow_relevance": ai_relevance,
        "full_stack_product_building_relevance": full_stack_relevance,
        "automation_workflow_relevance": automation_relevance,
        "technical_learning_opportunity": learning_opportunity,
        "product_venture_building_relevance": product_building_relevance,
        "personal_interest_fit": personal_interest_fit,
        "clarity_of_problem_and_icp": clarity_problem_icp,
        "evidence_available_from_bwe_content": evidence_available,
    }

    total_score = sum(criteria_scores.values())
    average_score = round(total_score / len(criteria_scores), 2)

    skills = _suggest_applicable_skills(venture_text)
    learn = _suggest_learning_areas(venture)
    contributions = _possible_contribution_ideas(venture, venture_text)
    why_aligns = (
        f"{venture.get('name', 'This venture')} aligns because it sits at the intersection of "
        f"{'AI/agentic systems' if ai_relevance >= 4 else 'product execution'} and "
        f"{'workflow automation' if automation_relevance >= 4 else 'practical software building'}. "
        f"The public description shows a clearer-than-average problem, ICP, and product wedge."
    )
    risks: list[str] = []
    if venture.get("technologies_mentioned") == "unknown":
        risks.append("Technology stack is not clearly described in the public content.")
    if not evidence["case_studies"]:
        risks.append("There is limited case-study depth, so product maturity is harder to judge.")
    if venture.get("target_users") == "unknown":
        risks.append("ICP detail is limited in the extracted record.")
    if not risks:
        risks.append("Public content may not reveal internal roadmap, maturity, or technical constraints.")

    return {
        "venture_name": venture.get("name", "unknown"),
        "sector": venture.get("sector", "unknown"),
        "product_type": venture.get("product_type", "unknown"),
        "alignment_score": total_score,
        "alignment_score_average": average_score,
        "criteria_scores": criteria_scores,
        "why_it_aligns_with_me": why_aligns,
        "skills_i_can_apply": skills,
        "what_i_can_learn": learn,
        "possible_contribution_ideas": contributions,
        "risks_or_unknowns": risks,
        "evidence_from_bwe_content": _alignment_evidence_text(venture, evidence),
        "source_url": venture.get("source_url", "unknown"),
    }


def build_personal_alignment() -> list[dict]:
    ventures = [
        venture
        for venture in load_json(VENTURES_PATH, [])
        if venture.get("name") not in {"Bold World Engineering", "The Best App Store"}
        and venture.get("sector") != "Venture Infrastructure"
    ]
    blogs = load_json(BLOGS_PATH, [])
    pages = load_json(PAGES_PATH, [])
    if not ventures:
        return []

    rankings: list[dict] = []
    for venture in ventures:
        evidence = _venture_evidence(venture, blogs, pages)
        ranked = _score_alignment(venture, evidence)
        rankings.append(ranked)

    rankings.sort(
        key=lambda item: (
            item["alignment_score"],
            item["criteria_scores"]["evidence_available_from_bwe_content"],
            item["criteria_scores"]["clarity_of_problem_and_icp"],
        ),
        reverse=True,
    )
    for index, item in enumerate(rankings, start=1):
        item["rank"] = index

    save_json(PERSONAL_ALIGNMENT_PATH, rankings)
    _write_report(REPORT_FILES["alignment"], _personal_alignment_report(rankings))
    return rankings


def _personal_alignment_report(rankings: list[dict]) -> str:
    profile_text = _load_personal_profile()
    top_five = rankings[:5]
    contribution_ideas = [
        "Build an internal AI workflow or copilot prototype for one of the highest-alignment ventures, then document the product and engineering tradeoffs.",
        "Create an operator-facing dashboard or workflow API layer that turns a venture's core process into a clearer execution loop.",
        "Ship a local-first research and reporting surface that helps a venture team test ICP assumptions, product wedges, or market gaps faster.",
    ]

    top_blocks = []
    for item in top_five:
        top_blocks.append(
            f"""### {item['rank']}. {item['venture_name']} — {item['alignment_score']}/40 ({item['alignment_score_average']}/5)

- **Why it aligns with my technical profile:** {item['why_it_aligns_with_me']}
- **What I could contribute:** {", ".join(item['possible_contribution_ideas'])}
- **What I should study before working on it:** {", ".join(item['what_i_can_learn'])}
- **Evidence from BWE content:** {item['evidence_from_bwe_content']}
- **Source URL:** {item['source_url']}
"""
        )

    full_blocks = []
    for item in rankings:
        scores = item["criteria_scores"]
        full_blocks.append(
            f"""### Venture Name: {item['venture_name']}
Sector: {item['sector']}
Product Type: {item['product_type']}
Alignment Score: {item['alignment_score']}/40 ({item['alignment_score_average']}/5)
Why it aligns with me: {item['why_it_aligns_with_me']}
Skills I can apply: {", ".join(item['skills_i_can_apply']) or 'unknown'}
What I can learn: {", ".join(item['what_i_can_learn']) or 'unknown'}
Possible contribution ideas: {", ".join(item['possible_contribution_ideas']) or 'unknown'}
Risks / Unknowns: {", ".join(item['risks_or_unknowns']) or 'unknown'}
Evidence from BWE content: {item['evidence_from_bwe_content']}
Source URL: {item['source_url']}

Criterion Scores:
- AI / agentic workflow relevance: {scores['ai_agentic_workflow_relevance']}/5
- Full-stack product-building relevance: {scores['full_stack_product_building_relevance']}/5
- Automation / workflow relevance: {scores['automation_workflow_relevance']}/5
- Technical learning opportunity: {scores['technical_learning_opportunity']}/5
- Product / venture-building relevance: {scores['product_venture_building_relevance']}/5
- Personal interest fit: {scores['personal_interest_fit']}/5
- Clarity of problem and ICP: {scores['clarity_of_problem_and_icp']}/5
- Evidence available from BWE content: {scores['evidence_available_from_bwe_content']}/5
"""
        )

    return f"""
# Personal Venture Alignment

{PERSONAL_ALIGNMENT_NOTE}

## Personal Profile

{profile_text}

## Top 5 Most Aligned Ventures

{"".join(top_blocks)}

## Why These Ventures Fit My Technical Profile

The top alignment set leans toward ventures with visible workflow friction, clearer operational systems, stronger public ICP definition, and enough product surface area for applied AI, full-stack shipping, and fast prototyping.

## Concrete Internship Contribution Ideas

{chr(10).join(f"- {idea}" for idea in contribution_ideas)}

## Full Ranked Venture Alignment Review

{"".join(full_blocks)}
"""


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


def _structured_alignment_answer(question: str) -> str | None:
    lowered = question.lower()
    if not any(token in lowered for token in ["align with me", "fit me", "my venture fit", "my profile"]):
        return None

    rankings = load_json(PERSONAL_ALIGNMENT_PATH, [])
    if not rankings:
        rankings = build_personal_alignment()
    if not rankings:
        return None

    top = rankings[:5]
    direct_answer = "The ventures that currently align most strongly with your profile are " + ", ".join(
        item["venture_name"] for item in top
    ) + "."
    reasoning = "They rank highest because they combine stronger AI or workflow relevance, clearer product problems and ICPs, and enough public evidence for contribution ideas to be concrete."
    sources = [item["source_url"] for item in top]
    supporting = [
        f"{item['venture_name']}: {item['alignment_score']}/40, skills={', '.join(item['skills_i_can_apply'][:4])}, learn={', '.join(item['what_i_can_learn'][:3])}."
        for item in top
    ]
    return _format_answer(
        direct_answer=direct_answer,
        reasoning=reasoning,
        inference_note=PERSONAL_ALIGNMENT_NOTE,
        sources=sources,
        supporting_excerpts=supporting,
    )


def _structured_answer(question: str) -> str | None:
    alignment_answer = _structured_alignment_answer(question)
    if alignment_answer:
        return alignment_answer

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
            "content, the strongest next-build directions appear to be compliance and diligence infrastructure, SMB "
            "operations automation, and founder back-office tooling."
        )
        reasoning = (
            "These themes recur across multiple ventures and reports: trust and compliance products such as Argus and ORBIT, "
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

    best_venture, _, _, _ = top[0]
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


def run_alignment() -> list[dict]:
    rankings = build_personal_alignment()
    print(f"Saved personal venture alignment for {len(rankings)} ventures to {REPORT_FILES['alignment']}")
    return rankings


def _vector_answer(question: str) -> str:
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


def run_ask(question: str, voice: str = "normal") -> str:
    structured = _structured_answer(question)
    if structured:
        return _apply_voice(structured, question, voice)

    if _is_strategy_question(question):
        return _apply_voice(_strategy_answer(question), question, voice)

    return _apply_voice(_vector_answer(question), question, voice)


__all__ = [
    "NOT_FOUND_MESSAGE",
    "PERSONAL_ALIGNMENT_NOTE",
    "build_personal_alignment",
    "generate_reports",
    "run_alignment",
    "run_analysis",
    "run_ask",
]
