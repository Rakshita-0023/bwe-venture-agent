from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

from ollama import Client

from config import BLOGS_PATH, PAGES_PATH, REPORT_FILES
from knowledge_base import get_runtime_models
from utils import load_json, normalize_whitespace


STYLE_GUIDE_FALLBACK = """# BWE Voice Style Guide

## BWE Voice Summary

BWE writes like a venture studio with builder conviction: direct, strategic, and grounded in visible operational friction.

## Tone

- Sharp and confident without sounding inflated
- Builder-led, execution-oriented, and fast-moving
- Concrete about pain, market reality, and product outcomes

## Common Writing Patterns

- Open with a clear friction point or market tension
- Tie the problem to a structural inefficiency, not just a feature gap
- Move quickly from problem to operating-system style solution framing
- Emphasize speed, proof, and practical execution

## Headline Patterns

- Strong declarative lines
- Contrast-led angles such as “problem -> better system”
- Specific market or workflow references rather than vague futurism

## Problem Framing

- Show the hidden tax, broken workflow, or trust gap
- Focus on operational drag, fragmented tools, or lost leverage
- Make the problem feel structural and urgent

## Solution Framing

- Position the product as an execution layer, operating system, copilot, or workflow engine
- Emphasize speed, clarity, and measurable reduction in friction
- Keep the solution language concise and commercially grounded

## Venture Positioning

- Anchor ventures in a clear ICP, a visible pain point, and a practical wedge
- Describe the product as something that changes how work gets done
- Prefer outcome language over feature sprawl

## Do

- Use concise, high-conviction language
- Name the workflow, the bottleneck, and the user
- Frame products as leverage systems

## Do Not

- Use generic “AI will change everything” language
- Drift into soft inspirational copy without operational detail
- Overstate claims that are not supported by visible evidence

## Example BWE-style Rewrite

Normal: Small firms struggle with fragmented compliance workflows and too much manual checking.

BWE-style: Compliance is not broken because teams lack effort. It breaks because diligence still lives across scattered workflows, slow checks, and trust gaps that do not scale.
"""


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "their",
    "they",
    "them",
    "have",
    "has",
    "about",
    "just",
    "more",
    "than",
    "when",
    "what",
    "where",
    "which",
    "will",
    "were",
    "been",
    "being",
    "because",
    "while",
    "through",
    "across",
    "over",
    "under",
    "into",
    "onto",
    "also",
    "then",
    "there",
    "here",
    "such",
    "like",
    "only",
    "some",
    "many",
    "much",
    "each",
    "very",
    "bwe",
    "studio",
}


def _load_style_sources() -> tuple[list[dict], list[dict]]:
    pages = load_json(PAGES_PATH, [])
    blogs = load_json(BLOGS_PATH, [])
    return pages, blogs


def _candidate_pages(pages: list[dict]) -> list[dict]:
    selected: list[dict] = []
    for page in pages:
        url = page.get("url", "")
        title = page.get("title", "")
        page_type = page.get("page_type", "")
        haystack = f"{url} {title} {page_type}".lower()
        if any(token in haystack for token in ["case-studies", "bwe-studio", "about", "hub", "blog", "insight"]):
            selected.append(page)
    return selected[:20]


def _collect_style_evidence() -> dict[str, object]:
    pages, blogs = _load_style_sources()
    selected_pages = _candidate_pages(pages)
    selected_blogs = blogs[:24]

    titles = [normalize_whitespace(str(blog.get("title", ""))) for blog in selected_blogs if blog.get("title")]
    summaries = [normalize_whitespace(str(blog.get("summary", ""))) for blog in selected_blogs if blog.get("summary")]
    page_excerpts = [
        normalize_whitespace(str(page.get("text", "")))[:380]
        for page in selected_pages
        if normalize_whitespace(str(page.get("text", "")))
    ]

    combined = " ".join(titles + summaries + page_excerpts)
    phrases = _top_phrases(combined)
    headline_patterns = _headline_patterns(titles)

    return {
        "titles": titles[:16],
        "summaries": summaries[:10],
        "page_excerpts": page_excerpts[:8],
        "common_phrases": phrases,
        "headline_patterns": headline_patterns,
    }


def _top_phrases(text: str, limit: int = 10) -> list[str]:
    tokens = [token.lower() for token in re.findall(r"[a-zA-Z][a-zA-Z&-]{2,}", text)]
    filtered = [token for token in tokens if token not in STOPWORDS]
    counts: Counter[str] = Counter()
    for size in (2, 3):
        for index in range(len(filtered) - size + 1):
            phrase = " ".join(filtered[index : index + size])
            if any(word in STOPWORDS for word in phrase.split()):
                continue
            counts[phrase] += 1
    ranked = [phrase for phrase, count in counts.most_common() if count > 1]
    return ranked[:limit]


def _headline_patterns(titles: list[str]) -> list[str]:
    patterns: Counter[str] = Counter()
    for title in titles:
        lowered = title.lower()
        if ":" in title:
            patterns["colon-led framing"] += 1
        if "?" in title:
            patterns["question headline"] += 1
        if any(word in lowered for word in ["why ", "how "]):
            patterns["explanatory thesis headline"] += 1
        if any(word in lowered for word in ["invisible", "tax", "future", "frontlines", "speed"]):
            patterns["high-contrast or urgency-led headline"] += 1
        if any(word in lowered for word in ["indian", "clinic", "car", "fund", "doctor"]):
            patterns["market-specific headline"] += 1
    return [pattern for pattern, _ in patterns.most_common(5)]


def _build_style_prompt(evidence: dict[str, object]) -> str:
    titles = "\n".join(f"- {title}" for title in evidence["titles"])
    summaries = "\n".join(f"- {summary}" for summary in evidence["summaries"])
    excerpts = "\n".join(f"- {excerpt}" for excerpt in evidence["page_excerpts"])
    phrases = ", ".join(evidence["common_phrases"])
    headline_patterns = ", ".join(evidence["headline_patterns"])
    return (
        "You are analyzing the writing voice of Bold World Engineering / BWE Studio.\n"
        "Use only the evidence below.\n"
        "Do not copy long passages. Do not plagiarize. Produce an original style guide.\n"
        "Keep it concise, strategic, and grounded.\n"
        "Use exactly these headings:\n"
        "## BWE Voice Summary\n"
        "## Tone\n"
        "## Common Writing Patterns\n"
        "## Headline Patterns\n"
        "## Problem Framing\n"
        "## Solution Framing\n"
        "## Venture Positioning\n"
        "## Do\n"
        "## Do Not\n"
        "## Example BWE-style Rewrite\n\n"
        "Evidence from blog titles:\n"
        f"{titles}\n\n"
        "Evidence from summaries:\n"
        f"{summaries}\n\n"
        "Evidence from pages/case studies:\n"
        f"{excerpts}\n\n"
        f"Observed common phrases: {phrases or 'none'}\n"
        f"Observed headline patterns: {headline_patterns or 'none'}\n\n"
        "Return markdown beginning with '# BWE Voice Style Guide'."
    )


def _deterministic_style_guide(evidence: dict[str, object]) -> str:
    common_phrases = evidence["common_phrases"][:6] or [
        "speed of code",
        "structural friction",
        "operating system",
        "real-world impact",
        "production-ready systems",
    ]
    headline_patterns = evidence["headline_patterns"] or [
        "market-specific headline",
        "explanatory thesis headline",
        "high-contrast or urgency-led headline",
    ]
    return f"""# BWE Voice Style Guide

## BWE Voice Summary

BWE writes with builder conviction. The voice is strategic, execution-led, and anchored in visible market friction rather than abstract innovation language.

## Tone

- Direct and commercially aware
- Confident without sounding inflated
- Fast-moving, systems-oriented, and product-first
- Comfortable naming urgency, friction, and operational drag

## Common Writing Patterns

- Opens with a sharp problem, hidden tax, or broken workflow
- Moves quickly from friction to a system-level response
- Frames products as operating systems, execution layers, copilots, or workflow engines
- Prefers practical outcomes over broad future-of-AI claims
- Recurring language signals: {", ".join(common_phrases)}

## Headline Patterns

- Observed headline patterns: {", ".join(headline_patterns)}
- Uses strong declarative or explanatory titles
- Often ties the story to a specific market, user, or operational pain point

## Problem Framing

- Problems are framed as structural friction, trust gaps, hidden operational costs, or fragmented workflows
- The writing makes the pain feel measurable and urgent
- It tends to zoom in on what the user is forced to do manually today

## Solution Framing

- Solutions are framed as systems that remove friction, compress execution time, or create leverage
- Product language is concise and outcome-oriented
- AI is described as a practical execution layer, not as magic

## Venture Positioning

- Ventures are positioned around a specific ICP, a clear pain point, and a sharp wedge
- The product story usually emphasizes how work gets done differently after adoption
- Positioning tends to connect product design to a broader market or operating thesis

## Do

- Write with clarity, urgency, and commercial sharpness
- Name the workflow, the bottleneck, and the user
- Position the product as leverage, not just a feature set
- Keep the language concise and operationally grounded

## Do Not

- Use vague innovation buzzwords or generic AI hype
- Drift into soft inspirational copy without a product point of view
- Overstate certainty when the source evidence is thin
- Copy long phrases from the original site content

## Example BWE-style Rewrite

Normal: Founders lose time because too many back-office tasks still sit across disconnected tools.

BWE-style: Founder drag does not look dramatic. It looks like revenue follow-up, invoicing, and operating admin leaking across disconnected workflows that never quite close the loop.
"""


def generate_style_guide() -> str:
    evidence = _collect_style_evidence()
    report_text = _deterministic_style_guide(evidence)

    if os.getenv("BWE_USE_OLLAMA_STYLE_GUIDE") == "1":
        prompt = _build_style_prompt(evidence)
        try:
            model = get_runtime_models()["llm_model"]
            response = Client().generate(model=model, prompt=prompt)
            candidate = response.get("response", "").strip() if isinstance(response, dict) else ""
            if candidate and "BWE Voice Style Guide" in candidate:
                report_text = candidate
        except Exception:
            report_text = report_text or STYLE_GUIDE_FALLBACK

    report_path = REPORT_FILES["style_guide"]
    report_path.write_text(report_text.strip() + "\n", encoding="utf-8")
    return report_text


def load_style_guide_text() -> str:
    path: Path = REPORT_FILES["style_guide"]
    if not path.exists():
        return generate_style_guide()
    return path.read_text(encoding="utf-8")


def rewrite_sections_in_bwe_voice(
    question: str,
    direct_answer: str,
    reasoning: str | None,
    inference_note: str | None,
) -> dict[str, str]:
    style_guide = load_style_guide_text()
    if os.getenv("BWE_USE_OLLAMA_VOICE") != "1":
        return _deterministic_bwe_rewrite(question, direct_answer, reasoning, inference_note, style_guide)

    prompt = (
        "Rewrite the answer in a BWE-style venture-studio voice while preserving facts.\n"
        "Rules:\n"
        "1. Do not add new claims.\n"
        "2. Keep it concise and sharp.\n"
        "3. Preserve any uncertainty.\n"
        "4. Avoid generic AI hype wording.\n"
        "5. Return exactly these headings:\n"
        "DIRECT_ANSWER:\nREASONING:\nINFERENCE_NOTE:\n\n"
        f"Question: {question}\n\n"
        f"Style guide:\n{style_guide}\n\n"
        f"Original direct answer:\n{direct_answer}\n\n"
        f"Original reasoning:\n{reasoning or 'unknown'}\n\n"
        f"Original inference note:\n{inference_note or 'unknown'}\n"
    )
    try:
        model = get_runtime_models()["llm_model"]
        response = Client().generate(model=model, prompt=prompt)
        content = response.get("response", "") if isinstance(response, dict) else ""
        return _parse_rewrite_sections(content, direct_answer, reasoning, inference_note)
    except Exception:
        return _deterministic_bwe_rewrite(question, direct_answer, reasoning, inference_note, style_guide)


def _deterministic_bwe_rewrite(
    question: str,
    direct_answer: str,
    reasoning: str | None,
    inference_note: str | None,
    style_guide: str,
) -> dict[str, str]:
    style_signals = []
    signal_map = {
        "structural friction": "structural friction",
        "operating system": "operating-system style products",
        "workflow": "workflow leverage",
        "execution layer": "execution layers",
        "leverage": "leverage-driven positioning",
    }
    for signal, label in signal_map.items():
        if signal in style_guide.lower():
            style_signals.append(label)

    direct = normalize_whitespace(direct_answer)
    reason = normalize_whitespace(reasoning or "")
    lowered_question = question.lower()

    if any(token in lowered_question for token in ["product thesis", "build next", "strongest fit"]):
        focus = _extract_focus_segment(direct)
        strategic_focus = focus or "compliance, diligence, SMB operations, and founder back-office workflows"
        direct = (
            f"BWE should keep building where the market still runs on messy human coordination: {strategic_focus}. "
            "The pattern is clear - repeated friction, fragmented tools, and high-value work trapped in manual processes. "
            "That is where an operating-system style product can create leverage."
        )
        if reason:
            sharpened_reason = _sharpen_reason(reason)
            if sharpened_reason.lower().startswith("the same thesis"):
                reason = sharpened_reason
            else:
                reason = (
                    "The public signal set keeps clustering around the same shape of opportunity: "
                    + sharpened_reason
                )
    elif any(token in lowered_question for token in ["best venture", "most promising", "which venture looks"]):
        venture_name = _extract_named_entity(direct) or "the leading venture in the current public set"
        direct = (
            f"{venture_name} stands out because the public story is tighter. "
            "The problem is clearer, the buyer is easier to see, and the product wedge has more visible proof around it."
        )
        if reason:
            reason = (
                "This is not about surface polish. It is about where the public evidence shows a cleaner line from friction to product to market."
            )
    elif any(token in lowered_question for token in ["align with me", "fit me", "my venture fit"]):
        direct = (
            f"The strongest fit for your profile sits where AI workflows, product systems, and execution leverage overlap: {direct[direct.find('are ')+4:] if 'are ' in direct else direct.lower()}".rstrip(".")
            + "."
        )
        if reason:
            reason = (
                "These ventures are a better personal match because the work is not just technical. "
                "It sits inside product wedges where fast prototyping, workflow design, and applied AI can all matter at once."
            )
    elif any(token in lowered_question for token in ["what does bold world engineering do", "what does bwe do", "what is bwe"]):
        direct = (
            "BWE looks less like a traditional studio and more like an execution layer for venture creation. "
            + _lower_first(direct)
        )
        if reason:
            reason = "The language across the site keeps reinforcing the same idea: venture building as fast system design, not just idea generation."
    else:
        if not direct.lower().startswith("from the public signal set"):
            direct = f"From the public signal set, {_lower_first(direct)}"
        if reason:
            reason = "The public evidence points in one direction: " + _sharpen_reason(reason)

    if style_signals and reason:
        reason += f" The style pattern behind that reading is consistent too: {', '.join(style_signals[:3])}."

    note = normalize_whitespace(inference_note or "")
    if note and "not an official bwe ranking" not in note.lower():
        note = note.rstrip(".") + ". This is an evidence-based inference, not an official BWE ranking."
    return {"direct_answer": direct, "reasoning": reason, "inference_note": note}


def _extract_focus_segment(text: str) -> str:
    patterns = [
        r"appear to be (.+)",
        r"are (.+)",
        r"include (.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = normalize_whitespace(match.group(1)).rstrip(".")
            return candidate
    return ""


def _extract_named_entity(text: str) -> str:
    match = re.search(r"([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*)*)", text)
    return normalize_whitespace(match.group(1)) if match else ""


def _lower_first(text: str) -> str:
    text = normalize_whitespace(text)
    if not text:
        return text
    return text[:1].lower() + text[1:]


def _sharpen_reason(reason: str) -> str:
    reason = normalize_whitespace(reason)
    replacements = {
        "These themes recur across multiple ventures and reports:": "The same thesis shows up again and again across the portfolio:",
        "This summary is based on": "That reading comes from",
        "because it shows stronger": "because the public material shows stronger",
        "clearer clarity of problem": "clearer problem definition",
    }
    for source, target in replacements.items():
        reason = reason.replace(source, target)
    return reason


def _parse_rewrite_sections(
    content: str,
    direct_answer: str,
    reasoning: str | None,
    inference_note: str | None,
) -> dict[str, str]:
    parsed = {"direct_answer": direct_answer, "reasoning": reasoning or "", "inference_note": inference_note or ""}
    current: str | None = None
    lines: list[str] = []
    mapping = {
        "DIRECT_ANSWER:": "direct_answer",
        "REASONING:": "reasoning",
        "INFERENCE_NOTE:": "inference_note",
    }
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line in mapping:
            if current:
                parsed[current] = normalize_whitespace("\n".join(lines)) or parsed[current]
            current = mapping[line]
            lines = []
            continue
        lines.append(raw_line)
    if current:
        parsed[current] = normalize_whitespace("\n".join(lines)) or parsed[current]
    return parsed
