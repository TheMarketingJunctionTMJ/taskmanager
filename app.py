from __future__ import annotations

import json
import os
import uuid
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from lib.anthropic_client import generate_text
from lib.export_docx import export_blog_docx
from lib.export_pdf import export_blog_pdf
from lib.file_processing import extract_text_from_upload
from lib.prompts import (
    LANGUAGE_OPTIONS,
    TONE_OPTIONS,
    ai_friendly_blog_system_prompt,
    ai_friendly_blog_user_prompt,
    ai_friendly_outline_system_prompt,
    ai_friendly_outline_user_prompt,
    evaluate_system_prompt,
    evaluate_user_prompt,
    insights_system_prompt,
    insights_user_prompt,
    outline_system_prompt,
    outline_user_prompt,
    revision_system_prompt,
    revision_user_prompt,
    section_system_prompt,
    section_user_prompt,
    verify_system_prompt,
    verify_user_prompt,
)

load_dotenv()

st.set_page_config(page_title="Streamlit Blog Studio", page_icon="✍️", layout="wide")


def init_state() -> None:
    defaults: dict[str, Any] = {
        "blog_mode": "Writer Version",
        "title": "",
        "topic": "",
        "audience": "",
        "keywords_text": "",
        "facts_text": "",
        "quotes_text": "",
        "research_notes": "",
        "tone": "Thought leadership",
        "language": "UK English",
        "target_words": 1200,
        "add_hiring_section": False,
        "document_text": "",
        "document_insights": [],
        "quoted_lines": [],
        "evaluated_evidence": {},
        "verified_evidence": {},
        "outline_title": "",
        "outline": [],
        "sections_content": {},
        "logo_bytes": None,
        "logo_name": "",
        "sections_workspace_ready": False,
        "new_section_prompt": "",
        "seo_keyword_suggestions": [],
        "selected_seo_keywords": [],
        "show_seo_keyword_dialog": False,
        "pending_outline_generation": False,
        "ai_friendly_draft": "",
        "ai_friendly_draft_editor": "",
        "pending_ai_friendly_generation": False,
        "ai_outline_title": "",
        "ai_outline": [],
        "ai_new_section_prompt": "",
        "pending_ai_outline_generation": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def lines_to_list(value: str) -> list[str]:
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def current_inputs() -> dict[str, Any]:
    return {
        "title": st.session_state.title.strip() or st.session_state.topic.strip(),
        "topic": st.session_state.topic.strip(),
        "audience": st.session_state.audience.strip(),
        "keywords": lines_to_list(st.session_state.keywords_text),
        "facts": lines_to_list(st.session_state.facts_text),
        "quotes": lines_to_list(st.session_state.quotes_text),
        "research_notes": st.session_state.research_notes.strip(),
        "tone": st.session_state.tone,
        "language": st.session_state.language,
        "target_words": int(st.session_state.target_words),
        "document_insights": st.session_state.document_insights,
        "verified_evidence": st.session_state.verified_evidence,
        "blog_mode": st.session_state.blog_mode,
        "add_hiring_section": bool(st.session_state.add_hiring_section),
    }


def parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def clean_text(text: str) -> str:
    text = str(text or "")
    text = text.replace("—", ", ")
    text = text.replace("–", ", ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def to_bullet_lines(items: list[str]) -> str:
    cleaned = []
    for item in items:
        text = clean_text(item).lstrip("- ").strip()
        if text:
            cleaned.append(f"- {text}")
    return "\n".join(cleaned)


def from_bullet_lines(value: str) -> list[str]:
    cleaned = []
    for line in lines_to_list(value):
        text = clean_text(line).lstrip("- ").strip()
        if text:
            cleaned.append(text)
    return cleaned


def calc_text_area_height(text: str, min_height: int = 140, line_px: int = 28, extra_lines: int = 2) -> int:
    line_count = max(1, str(text or "").count("\n") + 1 + extra_lines)
    return max(min_height, line_px * line_count)


def normalise_heading_for_compare(text: str) -> str:
    text = clean_text(text).lower()
    chars: list[str] = []
    previous_was_space = False
    for char in text:
        if char.isalnum():
            chars.append(char)
            previous_was_space = False
        else:
            if not previous_was_space:
                chars.append(" ")
                previous_was_space = True
    return " ".join("".join(chars).split())


def strip_leading_heading(content: str, heading: str) -> str:
    content = str(content or "")
    heading = clean_text(heading)
    if not content.strip() or not heading:
        return clean_text(content)

    lines = content.splitlines()
    first_non_empty_index = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_non_empty_index = idx
            break

    if first_non_empty_index is None:
        return clean_text(content)

    first_line = lines[first_non_empty_index].strip()
    candidate = first_line.lstrip("#").strip()
    candidate = candidate.strip("*_").strip()
    candidate = candidate.rstrip(":")

    if normalise_heading_for_compare(candidate) == normalise_heading_for_compare(heading):
        remaining_lines = lines[first_non_empty_index + 1:]
        while remaining_lines and not remaining_lines[0].strip():
            remaining_lines.pop(0)
        return clean_text("\n".join(remaining_lines))

    return clean_text(content)


def sanitise_section_content(content: str, heading: str) -> str:
    return strip_leading_heading(clean_text(content), heading)


def section_max_tokens(suggested_words: int) -> int:
    target = max(80, int(suggested_words))
    return min(1400, max(250, int(target * 1.35)))


def count_words_in_sections(ordered_sections: list[dict[str, str]]) -> int:
    total_text = " ".join(
        clean_text(section.get("content", ""))
        for section in ordered_sections
        if clean_text(section.get("content", ""))
    )
    return len(total_text.split())


def build_export_sections_with_appendix(
    ordered_sections: list[dict[str, str]],
    keywords: list[str],
) -> list[dict[str, str]]:
    total_words = count_words_in_sections(ordered_sections)
    cleaned_keywords = [clean_text(keyword) for keyword in keywords if clean_text(keyword)]

    appendix_lines = [f"Total number of words: {total_words}"]

    if cleaned_keywords:
        appendix_lines.append("SEO keywords used: " + ", ".join(cleaned_keywords))
    else:
        appendix_lines.append("SEO keywords used: None provided")

    export_sections = list(ordered_sections)
    export_sections.append(
        {
            "heading": "Article metadata",
            "content": "\n\n".join(appendix_lines),
        }
    )
    return export_sections


def markdown_to_export_sections(markdown_text: str, fallback_title: str) -> list[dict[str, str]]:
    text = str(markdown_text or "").strip()
    if not text:
        return [{"heading": fallback_title or "Article", "content": ""}]

    sections: list[dict[str, str]] = []
    current_heading = fallback_title or "Article"
    current_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            if current_lines:
                sections.append(
                    {
                        "heading": clean_text(current_heading),
                        "content": "\n".join(current_lines).strip(),
                    }
                )
            current_heading = clean_text(line[3:])
            current_lines = []
        elif line.startswith("# "):
            if not sections and not current_lines:
                current_heading = clean_text(line[2:])
            else:
                current_lines.append(line)
        else:
            current_lines.append(line)

    if current_lines or not sections:
        sections.append(
            {
                "heading": clean_text(current_heading),
                "content": "\n".join(current_lines).strip(),
            }
        )

    cleaned_sections = []
    for section in sections:
        heading = clean_text(section.get("heading", "")) or "Section"
        content = clean_text(section.get("content", ""))
        if content:
            cleaned_sections.append({"heading": heading, "content": content})

    if not cleaned_sections:
        cleaned_sections.append({"heading": fallback_title or "Article", "content": text})

    return cleaned_sections


def make_section_id() -> str:
    return f"s{uuid.uuid4().hex[:8]}"


def build_manual_section(prompt: str) -> dict[str, Any]:
    prompt = clean_text(prompt)
    words = [word for word in prompt.replace(",", " ").split() if word]
    heading = " ".join(words[:12]).strip().rstrip(".") or "New section"
    heading = heading[:1].upper() + heading[1:] if heading else "New section"
    return {
        "id": make_section_id(),
        "heading": heading,
        "objective": prompt,
        "keyPoints": [prompt],
        "suggestedWords": 180,
    }


def build_evidence_bundle(inputs: dict[str, Any]) -> str:
    parts: list[str] = []

    if inputs["facts"]:
        parts.append("User facts:\n" + "\n".join(f"- {clean_text(x)}" for x in inputs["facts"] if clean_text(x)))

    if inputs["quotes"]:
        parts.append("User quotes:\n" + "\n".join(f"- {clean_text(x)}" for x in inputs["quotes"] if clean_text(x)))

    if inputs["research_notes"]:
        parts.append("Research notes:\n" + clean_text(inputs["research_notes"]))

    if st.session_state.document_text.strip():
        parts.append("Uploaded document text:\n" + st.session_state.document_text[:12000])

    return "\n\n".join(parts).strip()


def suggest_seo_keywords(inputs: dict[str, Any]) -> list[str]:
    topic = clean_text(inputs["topic"] or inputs["title"] or "blog topic")
    audience = clean_text(inputs["audience"])

    system_prompt = (
        f"You are an SEO strategist writing in {inputs['language']}. "
        "Return valid JSON only."
    )

    user_prompt = f"""
Suggest 12 SEO keywords or keyword phrases for this blog article.

Topic: {topic}
Audience: {audience}
Tone: {inputs['tone']}

Return JSON in this shape:
{{
  "keywords": [
    "keyword 1",
    "keyword 2",
    "keyword 3"
  ]
}}

Rules:
- Return exactly 12 suggestions.
- Mix short-tail and long-tail phrases.
- Keep them relevant to the topic and audience.
- No numbering.
- No markdown.
- JSON only.
"""
    response = generate_text(system_prompt, user_prompt, max_tokens=700)
    parsed = parse_json_response(response)
    return [clean_text(item) for item in parsed.get("keywords", []) if clean_text(item)][:12]


def run_evan_light(inputs: dict[str, Any]) -> None:
    evidence_text = build_evidence_bundle(inputs)

    if not evidence_text:
        st.session_state.evaluated_evidence = {}
        st.session_state.verified_evidence = {}
        return

    evaluated_response = generate_text(
        evaluate_system_prompt(inputs["language"]),
        evaluate_user_prompt(
            evidence_text,
            inputs["topic"] or inputs["title"] or "blog topic",
            inputs["language"],
        ),
        max_tokens=1800,
    )
    evaluated = parse_json_response(evaluated_response)

    verified_response = generate_text(
        verify_system_prompt(inputs["language"]),
        verify_user_prompt(
            json.dumps(evaluated, ensure_ascii=False),
            evidence_text,
            inputs["topic"] or inputs["title"] or "blog topic",
            inputs["language"],
        ),
        max_tokens=1800,
    )
    verified = parse_json_response(verified_response)

    st.session_state.evaluated_evidence = evaluated
    st.session_state.verified_evidence = verified


def run_outline_generation() -> None:
    st.session_state.pending_outline_generation = False

    inputs = current_inputs()
    if not inputs["topic"]:
        st.error("Please enter a topic first.")
        return

    run_evan_light(inputs)
    inputs = current_inputs()

    response = generate_text(
        outline_system_prompt(inputs["language"]),
        outline_user_prompt(inputs),
        max_tokens=2200,
    )
    parsed = parse_json_response(response)
    st.session_state.outline_title = clean_text(
        parsed.get("title") or inputs["title"] or inputs["topic"]
    )
    st.session_state.outline = parsed.get("outline", [])
    st.session_state.sections_content = {}
    st.session_state.sections_workspace_ready = False
    st.session_state.new_section_prompt = ""
    st.session_state.ai_friendly_draft = ""
    st.session_state.ai_friendly_draft_editor = ""

    keys_to_delete = [
        key
        for key in list(st.session_state.keys())
        if key.startswith("content_") or key.startswith("rev_inst_")
    ]
    for key in keys_to_delete:
        del st.session_state[key]

    normalise_outline()
    st.session_state.show_seo_keyword_dialog = False
    st.success("Outline generated.")
    st.rerun()


def run_ai_outline_generation() -> None:
    st.session_state.pending_ai_outline_generation = False

    inputs = current_inputs()
    if not inputs["topic"]:
        st.error("Please enter a topic first.")
        return

    run_evan_light(inputs)
    inputs = current_inputs()

    response = generate_text(
        ai_friendly_outline_system_prompt(inputs["language"]),
        ai_friendly_outline_user_prompt(inputs),
        max_tokens=2400,
    )
    parsed = parse_json_response(response)

    st.session_state.ai_outline_title = clean_text(
        parsed.get("title") or inputs["title"] or inputs["topic"]
    )
    st.session_state.ai_outline = parsed.get("outline", [])
    st.session_state.ai_new_section_prompt = ""
    st.session_state.ai_friendly_draft = ""
    st.session_state.ai_friendly_draft_editor = ""

    normalise_ai_outline()
    st.session_state.show_seo_keyword_dialog = False
    st.success("AI-friendly outline generated.")
    st.rerun()


def serialise_outline_for_prompt(outline: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for idx, section in enumerate(outline, start=1):
        heading = clean_text(section.get("heading", ""))
        objective = clean_text(section.get("objective", ""))
        suggested_words = int(section.get("suggestedWords", 180))
        key_points = [clean_text(point) for point in section.get("keyPoints", []) if clean_text(point)]

        lines.append(f"Section {idx}: {heading}")
        lines.append(f"Objective: {objective}")
        lines.append(f"Suggested words: {suggested_words}")
        if key_points:
            lines.append("Key points:")
            lines.extend(f"- {point}" for point in key_points)
        else:
            lines.append("Key points:\n- None provided")
        lines.append("")

    return "\n".join(lines).strip()


def run_ai_friendly_generation() -> None:
    st.session_state.pending_ai_friendly_generation = False

    inputs = current_inputs()
    if not inputs["topic"]:
        st.error("Please enter a topic first.")
        return

    run_evan_light(inputs)
    inputs = current_inputs()

    seo_keywords = [clean_text(keyword) for keyword in inputs["keywords"] if clean_text(keyword)]
    outline = st.session_state.get("ai_outline", []) or []
    outline_title = clean_text(
        st.session_state.get("ai_outline_title") or inputs["title"] or inputs["topic"] or "Article"
    )

    keyword_instruction = ""
    keyword_footer = ""

    if seo_keywords:
        keyword_instruction = (
            "\n\nAdditional SEO requirement:\n"
            "Use every SEO keyword or phrase below naturally at least once where relevant.\n"
            "Do not keyword-stuff, but do not omit them.\n"
            + "\n".join(f"- {keyword}" for keyword in seo_keywords)
        )

        keyword_footer = "\n\n## SEO keywords used\n\n" + "\n".join(
            f"- {keyword}" for keyword in seo_keywords
        )

    response = generate_text(
        ai_friendly_blog_system_prompt(inputs["language"]),
        ai_friendly_blog_user_prompt(
            inputs,
            outline_title=outline_title,
            outline=outline,
        ) + keyword_instruction,
        max_tokens=3800,
    )

    final_draft = response.strip()
    if keyword_footer:
        final_draft = f"{final_draft}{keyword_footer}"

    st.session_state.ai_friendly_draft = final_draft
    st.session_state.ai_friendly_draft_editor = final_draft
    st.success("AI-friendly blog generated.")
    st.rerun()


def generate_new_section_from_prompt(one_liner: str) -> dict[str, Any]:
    inputs = current_inputs()
    article_title = clean_text(st.session_state.outline_title or inputs["title"] or inputs["topic"] or "the article")
    existing_headings = [clean_text(section.get("heading", "")) for section in st.session_state.outline if clean_text(section.get("heading", ""))]

    system_prompt = (
        f"You are an expert blog strategist writing in {inputs['language']}. "
        "Return valid JSON only."
    )
    user_prompt = f"""
Create exactly one new blog section for this article.

Article title: {article_title}
Topic: {inputs['topic']}
Audience: {inputs['audience']}
Tone: {inputs['tone']}
Target words for whole article: {inputs['target_words']}
Existing section headings: {json.dumps(existing_headings, ensure_ascii=False)}
Requested new section idea: {one_liner}

Return JSON in this shape:
{{
  "heading": "...",
  "objective": "...",
  "keyPoints": ["...", "...", "..."],
  "suggestedWords": 180
}}

Rules:
- Make the new section distinct from the existing headings.
- Keep the heading concise and publication-ready.
- Objective should be one clear sentence.
- keyPoints should contain 3 short bullets.
- suggestedWords must be an integer between 120 and 350.
- No markdown, no commentary, JSON only.
"""
    response = generate_text(system_prompt, user_prompt, max_tokens=900)
    parsed = parse_json_response(response)
    return {
        "id": make_section_id(),
        "heading": clean_text(parsed.get("heading", "") or one_liner),
        "objective": clean_text(parsed.get("objective", "") or one_liner),
        "keyPoints": [clean_text(point) for point in parsed.get("keyPoints", []) if clean_text(point)],
        "suggestedWords": int(parsed.get("suggestedWords", 180)),
    }


def generate_new_ai_section_from_prompt(one_liner: str) -> dict[str, Any]:
    inputs = current_inputs()
    article_title = clean_text(
        st.session_state.ai_outline_title or inputs["title"] or inputs["topic"] or "the article"
    )
    existing_headings = [
        clean_text(section.get("heading", ""))
        for section in st.session_state.ai_outline
        if clean_text(section.get("heading", ""))
    ]

    system_prompt = (
        f"You are an expert blog strategist writing in {inputs['language']}. "
        "Return valid JSON only."
    )
    user_prompt = f"""
Create exactly one new AI-friendly blog section for this article.

Article title: {article_title}
Topic: {inputs['topic']}
Audience: {inputs['audience']}
Tone: {inputs['tone']}
Target words for whole article: {inputs['target_words']}
Existing section headings: {json.dumps(existing_headings, ensure_ascii=False)}
Requested new section idea: {one_liner}

Return JSON in this shape:
{{
  "heading": "...",
  "objective": "...",
  "keyPoints": ["...", "...", "..."],
  "suggestedWords": 180
}}

Rules:
- Make the heading question-led or answer-led where appropriate for an AI-friendly blog.
- Make the new section distinct from the existing headings.
- Keep the heading concise and publication-ready.
- Objective should be one clear sentence.
- keyPoints should contain 3 short bullets.
- suggestedWords must be an integer between 120 and 350.
- No markdown, no commentary, JSON only.
"""
    response = generate_text(system_prompt, user_prompt, max_tokens=900)
    parsed = parse_json_response(response)
    return {
        "id": make_section_id(),
        "heading": clean_text(parsed.get("heading", "") or one_liner),
        "objective": clean_text(parsed.get("objective", "") or one_liner),
        "keyPoints": [clean_text(point) for point in parsed.get("keyPoints", []) if clean_text(point)],
        "suggestedWords": int(parsed.get("suggestedWords", 180)),
    }


def delete_section(section_id: str) -> None:
    st.session_state.outline = [
        section for section in st.session_state.outline if str(section.get("id")) != str(section_id)
    ]
    st.session_state.sections_content.pop(section_id, None)
    st.session_state.pop(f"content_{section_id}", None)
    st.session_state.pop(f"rev_inst_{section_id}", None)
    normalise_outline()
    if not st.session_state.outline:
        st.session_state.sections_workspace_ready = False


def delete_ai_section(section_id: str) -> None:
    st.session_state.ai_outline = [
        section for section in st.session_state.ai_outline if str(section.get("id")) != str(section_id)
    ]
    normalise_ai_outline()


def normalise_outline() -> None:
    cleaned_outline: list[dict[str, Any]] = []

    valid_section_ids: set[str] = set()
    for idx, section in enumerate(st.session_state.outline):
        section_id = str(section.get("id") or f"s{idx+1}")
        valid_section_ids.add(section_id)
        cleaned_outline.append(
            {
                "id": section_id,
                "heading": clean_text(section.get("heading", "")),
                "objective": clean_text(section.get("objective", "")),
                "keyPoints": [
                    clean_text(point).lstrip("- ").strip()
                    for point in section.get("keyPoints", [])
                    if clean_text(point).lstrip("- ").strip()
                ],
                "suggestedWords": max(80, int(section.get("suggestedWords", 180))),
            }
        )
        st.session_state.sections_content.setdefault(section_id, "")

    stale_ids = [section_id for section_id in list(st.session_state.sections_content.keys()) if section_id not in valid_section_ids]
    for stale_id in stale_ids:
        st.session_state.sections_content.pop(stale_id, None)
        st.session_state.pop(f"content_{stale_id}", None)
        st.session_state.pop(f"rev_inst_{stale_id}", None)

    st.session_state.outline = cleaned_outline


def normalise_ai_outline() -> None:
    cleaned_outline: list[dict[str, Any]] = []

    for idx, section in enumerate(st.session_state.ai_outline):
        section_id = str(section.get("id") or f"s{idx+1}")
        cleaned_outline.append(
            {
                "id": section_id,
                "heading": clean_text(section.get("heading", "")),
                "objective": clean_text(section.get("objective", "")),
                "keyPoints": [
                    clean_text(point).lstrip("- ").strip()
                    for point in section.get("keyPoints", [])
                    if clean_text(point).lstrip("- ").strip()
                ],
                "suggestedWords": max(80, int(section.get("suggestedWords", 180))),
            }
        )

    st.session_state.ai_outline = cleaned_outline


def generate_missing_sections(inputs: dict[str, Any], title: str) -> bool:
    generated_any = False
    for section in st.session_state.outline:
        key = section["id"]
        existing = clean_text(st.session_state.sections_content.get(key, ""))
        if existing:
            continue

        tighter_section = dict(section)
        tighter_section["objective"] = (
            f"{clean_text(section.get('objective', ''))} "
            f"Write approximately {int(section['suggestedWords'])} words. "
            f"Do not exceed the target by more than 120 words."
        ).strip()

        section_text = sanitise_section_content(
            generate_text(
                section_system_prompt(inputs["language"]),
                section_user_prompt(inputs, tighter_section, title, st.session_state.outline),
                max_tokens=section_max_tokens(int(section["suggestedWords"])),
            ),
            section.get("heading", ""),
        )

        st.session_state.sections_content[key] = section_text
        st.session_state[f"content_{key}"] = section_text
        generated_any = True

    return generated_any


def apply_pending_content_updates() -> None:
    pending_generation = st.session_state.pop("pending_generation_update", None)
    if pending_generation:
        section_id = str(pending_generation.get("section_id", "")).strip()
        generated_text = clean_text(pending_generation.get("content", ""))

        if section_id:
            matched_section = next((section for section in st.session_state.outline if str(section.get("id")) == section_id), None)
            heading = clean_text((matched_section or {}).get("heading", ""))
            generated_text = sanitise_section_content(generated_text, heading)
            content_key = f"content_{section_id}"
            st.session_state[content_key] = generated_text
            st.session_state.sections_content[section_id] = generated_text
            st.session_state["generation_success_message"] = "Section generated."

    pending_revision = st.session_state.pop("pending_revision_update", None)
    if pending_revision:
        section_id = str(pending_revision.get("section_id", "")).strip()
        revised_text = clean_text(pending_revision.get("content", ""))

        if section_id:
            matched_section = next((section for section in st.session_state.outline if str(section.get("id")) == section_id), None)
            heading = clean_text((matched_section or {}).get("heading", ""))
            revised_text = sanitise_section_content(revised_text, heading)
            content_key = f"content_{section_id}"
            st.session_state[content_key] = revised_text
            st.session_state.sections_content[section_id] = revised_text
            st.session_state["revision_success_message"] = "Section revised."


def switch_blog_mode(mode: str) -> None:
    if st.session_state.blog_mode == mode:
        return
    st.session_state.blog_mode = mode


init_state()
apply_pending_content_updates()
normalise_outline()
normalise_ai_outline()

if st.session_state.get("pending_outline_generation"):
    with st.spinner("Generating outline..."):
        run_outline_generation()

if st.session_state.get("pending_ai_outline_generation"):
    with st.spinner("Generating AI-friendly outline..."):
        run_ai_outline_generation()

if st.session_state.get("pending_ai_friendly_generation"):
    with st.spinner("Generating AI-friendly blog..."):
        run_ai_friendly_generation()

if st.session_state.show_seo_keyword_dialog:
    @st.dialog("Choose recommended SEO keywords")
    def seo_keywords_dialog() -> None:
        st.write("Your SEO keywords box is empty. Pick any recommended keywords below, then continue.")

        suggestions = st.session_state.get("seo_keyword_suggestions", [])
        selected = st.session_state.get("selected_seo_keywords", [])

        if not suggestions:
            st.info("No SEO suggestions are available right now.")
        else:
            cols_per_row = 3
            for start in range(0, len(suggestions), cols_per_row):
                cols = st.columns(cols_per_row)
                for idx, keyword in enumerate(suggestions[start:start + cols_per_row]):
                    is_selected = keyword in selected
                    button_label = f"✅ {keyword}" if is_selected else keyword
                    button_type = "primary" if is_selected else "secondary"

                    with cols[idx]:
                        if st.button(
                            button_label,
                            key=f"seo_pick_{start}_{idx}",
                            use_container_width=True,
                            type=button_type,
                        ):
                            if is_selected:
                                st.session_state.selected_seo_keywords = [
                                    item for item in st.session_state.selected_seo_keywords if item != keyword
                                ]
                            else:
                                st.session_state.selected_seo_keywords = [
                                    *st.session_state.selected_seo_keywords,
                                    keyword,
                                ]
                            st.rerun()

        action_col1, action_col2 = st.columns(2)

        with action_col1:
            if st.button("Cancel", use_container_width=True):
                st.session_state.show_seo_keyword_dialog = False
                st.rerun()

        with action_col2:
            if st.button("Continue", use_container_width=True, type="primary"):
                selected_keywords = st.session_state.get("selected_seo_keywords", [])

                if not selected_keywords:
                    st.warning("Please select at least one SEO keyword.")
                else:
                    st.session_state.keywords_text = "\n".join(selected_keywords)
                    st.session_state.selected_seo_keywords = selected_keywords
                    st.session_state.show_seo_keyword_dialog = False
                    if st.session_state.blog_mode == "Writer Version":
                        st.session_state.pending_outline_generation = True
                    else:
                        st.session_state.pending_ai_outline_generation = True
                    st.rerun()

    seo_keywords_dialog()

st.markdown(
    """
    <style>
    .mode-card {
        border: 1px solid rgba(49, 51, 63, 0.2);
        border-radius: 18px;
        padding: 18px 18px 14px 18px;
        background: #ffffff;
        min-height: 150px;
        box-shadow: 0 1px 6px rgba(0,0,0,0.04);
    }
    .mode-card.selected {
        border: 2px solid #4f46e5;
        box-shadow: 0 4px 18px rgba(79,70,229,0.10);
        background: #f7f7ff;
    }
    .mode-title {
        font-size: 1.15rem;
        font-weight: 700;
        margin-bottom: 8px;
    }
    .mode-copy {
        color: #4b5563;
        font-size: 0.94rem;
        line-height: 1.45;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

top_left, top_right = st.columns([1, 5])

with top_left:
    logo_upload = st.file_uploader(
        "Upload logo",
        type=["png", "jpg", "jpeg", "webp"],
        key="logo_uploader",
        help="Optional logo shown at the top of the app",
    )
    if logo_upload is not None:
        st.session_state.logo_bytes = logo_upload.getvalue()
        st.session_state.logo_name = logo_upload.name

with top_right:
    if st.session_state.logo_bytes:
        st.image(st.session_state.logo_bytes, width=180)

st.title("✍️ Streamlit Blog Studio")
st.caption("Create editorial blogs or AI-friendly, answer-style blog posts from one workspace")

if not os.getenv("ANTHROPIC_API_KEY"):
    st.error("ANTHROPIC_API_KEY is missing. Add it in your environment before using the app.")

st.subheader("Choose blog mode")
mode_col1, mode_col2 = st.columns(2)

with mode_col1:
    selected_class = "mode-card selected" if st.session_state.blog_mode == "Writer Version" else "mode-card"
    st.markdown(
        f"""
        <div class="{selected_class}">
            <div class="mode-title">Writer Version</div>
            <div class="mode-copy">
                Editorial, outline-first workflow for polished human-style content.<br><br>
                Best for: structured planning, section-by-section writing, revision control.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(
        "Use Writer Version",
        key="mode_writer",
        use_container_width=True,
        type="primary" if st.session_state.blog_mode == "Writer Version" else "secondary",
    ):
        switch_blog_mode("Writer Version")
        st.rerun()

with mode_col2:
    selected_class = "mode-card selected" if st.session_state.blog_mode == "AI Friendly" else "mode-card"
    st.markdown(
        f"""
        <div class="{selected_class}">
            <div class="mode-title">AI Friendly</div>
            <div class="mode-copy">
                Direct full-draft generation using question-led, skimmable, answer-engine-friendly structure.<br><br>
                Best for: quick production, search visibility, FAQ-rich blog layouts.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(
        "Use AI Friendly",
        key="mode_ai",
        use_container_width=True,
        type="primary" if st.session_state.blog_mode == "AI Friendly" else "secondary",
    ):
        switch_blog_mode("AI Friendly")
        st.rerun()

left, right = st.columns([1.1, 1])

with left:
    st.subheader("1. Blog setup")
    st.text_input("Topic", key="topic", placeholder="e.g. How AI is changing recruitment marketing")
    st.text_input("Working title", key="title", placeholder="Optional title override")
    st.text_input("Audience", key="audience", placeholder="e.g. Talent leaders at mid-size companies")
    st.selectbox("Tone", TONE_OPTIONS, key="tone")
    st.selectbox("Language", LANGUAGE_OPTIONS, key="language")
    st.slider("Target words", min_value=600, max_value=2500, step=100, key="target_words")
    st.checkbox("Do you want to add a hiring section?", key="add_hiring_section", help="If checked, the blog will include at least one section covering the impact on hiring.")
    st.text_area("SEO keywords (one per line)", key="keywords_text", height=140)

    st.subheader("2. Facts, quotes, and notes")
    st.text_area("Facts to include (one per line)", key="facts_text", height=160)
    st.text_area("Quotes to include verbatim (one per line)", key="quotes_text", height=160)
    st.text_area("Additional research notes", key="research_notes", height=160)

    st.subheader("3. Upload research")
    uploaded = st.file_uploader(
        "Upload PDF, DOCX, TXT, CSV, XLSX",
        type=["pdf", "docx", "txt", "csv", "xlsx", "xls"],
    )

    if uploaded is not None:
        if st.button("Extract insights from uploaded file"):
            try:
                raw_text = extract_text_from_upload(uploaded.name, uploaded.getvalue())
                st.session_state.document_text = raw_text
                response = generate_text(
                    insights_system_prompt(st.session_state.language),
                    insights_user_prompt(
                        raw_text,
                        st.session_state.topic or st.session_state.title or "blog topic",
                        st.session_state.language,
                    ),
                    max_tokens=1800,
                )
                parsed = parse_json_response(response)
                st.session_state.document_insights = parsed.get("insights", [])[:12]
                st.session_state.quoted_lines = parsed.get("quoted_lines", [])[:12]
                st.success("Document insights extracted.")
            except Exception as exc:
                st.error(f"Could not process upload: {exc}")

    if st.session_state.document_insights:
        st.markdown("**Document insights**")
        for item in st.session_state.document_insights:
            st.write(f"- {item}")

with right:
    if st.session_state.blog_mode == "Writer Version":
        st.subheader("4. Outline")
        if st.button("Generate outline", type="primary"):
            try:
                inputs = current_inputs()
                if not inputs["topic"]:
                    st.error("Please enter a topic first.")
                elif not inputs["keywords"]:
                    suggested_keywords = suggest_seo_keywords(inputs)
                    st.session_state.seo_keyword_suggestions = suggested_keywords
                    st.session_state.selected_seo_keywords = []
                    st.session_state.show_seo_keyword_dialog = True
                    st.rerun()
                else:
                    run_outline_generation()
            except Exception as exc:
                st.error(f"Could not generate outline: {exc}")

        verified = st.session_state.get("verified_evidence", {}) or {}
        if verified.get("verified_points") or verified.get("verified_quotes"):
            with st.expander("Verified evidence used for planning", expanded=False):
                if verified.get("verified_points"):
                    st.markdown("**Verified points**")
                    for item in verified.get("verified_points", [])[:10]:
                        st.write(f"- {item}")
                if verified.get("verified_quotes"):
                    st.markdown("**Verified quotes**")
                    for item in verified.get("verified_quotes", [])[:6]:
                        st.write(f"- {item}")
                if verified.get("unsupported_points"):
                    st.markdown("**Unsupported or weak points**")
                    for item in verified.get("unsupported_points", [])[:6]:
                        st.write(f"- {item}")

        if st.session_state.outline:
            st.text_input("Final article title", key="outline_title")
            st.caption("You can edit any heading or objective before generating sections.")

            with st.form("add_section_form", clear_on_submit=True):
                add_prompt_col, add_button_col = st.columns([4, 1.2])
                with add_prompt_col:
                    new_section_prompt = st.text_input(
                        "Add section with a one-line prompt",
                        key="new_section_prompt",
                        placeholder="e.g. Add a section on implementation mistakes teams should avoid",
                    )
                with add_button_col:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    add_section_submitted = st.form_submit_button("Add section", use_container_width=True)

                if add_section_submitted:
                    one_liner = clean_text(new_section_prompt)
                    if not one_liner:
                        st.error("Enter a one-line prompt for the new section.")
                    else:
                        try:
                            new_section = generate_new_section_from_prompt(one_liner)
                        except Exception:
                            new_section = build_manual_section(one_liner)

                        st.session_state.outline.append(new_section)
                        normalise_outline()
                        st.session_state.sections_workspace_ready = True
                        st.success("Section added.")
                        st.rerun()

            updated_outline: list[dict[str, Any]] = []
            delete_section_id: str | None = None
            for idx, section in enumerate(st.session_state.outline):
                with st.expander(f"Section {idx + 1}: {section.get('heading', 'Untitled')}", expanded=(idx == 0)):
                    heading = st.text_input(
                        f"Heading {idx + 1}",
                        value=clean_text(section.get("heading", "")),
                        key=f"heading_{idx}",
                    )

                    objective_value = clean_text(section.get("objective", ""))
                    objective_height = calc_text_area_height(
                        objective_value,
                        min_height=140,
                        line_px=28,
                        extra_lines=3,
                    )
                    objective = st.text_area(
                        f"Objective {idx + 1}",
                        value=objective_value,
                        key=f"objective_{idx}",
                        height=objective_height,
                    )

                    key_points_value = to_bullet_lines(section.get("keyPoints", []))
                    key_points_height = calc_text_area_height(
                        key_points_value,
                        min_height=170,
                        line_px=30,
                        extra_lines=3,
                    )
                    key_points_text = st.text_area(
                        f"Key points {idx + 1}",
                        value=key_points_value,
                        key=f"keypoints_{idx}",
                        height=key_points_height,
                    )

                    section_controls_col1, section_controls_col2 = st.columns([1.2, 1])
                    with section_controls_col1:
                        suggested_words = st.number_input(
                            f"Suggested words {idx + 1}",
                            min_value=80,
                            max_value=800,
                            value=int(section.get("suggestedWords", 180)),
                            step=20,
                            key=f"words_{idx}",
                        )
                    with section_controls_col2:
                        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                        if st.button("Delete section", key=f"delete_outline_{section['id']}", use_container_width=True):
                            delete_section_id = str(section["id"])

                    updated_outline.append(
                        {
                            "id": section.get("id", f"s{idx+1}"),
                            "heading": clean_text(heading),
                            "objective": clean_text(objective),
                            "keyPoints": from_bullet_lines(key_points_text),
                            "suggestedWords": int(suggested_words),
                        }
                    )

            st.session_state.outline = updated_outline
            normalise_outline()

            if delete_section_id:
                delete_section(delete_section_id)
                st.success("Section deleted.")
                st.rerun()

            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            prepare_col1, prepare_col2 = st.columns([1.5, 3])
            with prepare_col1:
                if st.button("Generate sections", use_container_width=True):
                    try:
                        st.session_state.sections_workspace_ready = True
                        inputs = current_inputs()
                        title = clean_text(st.session_state.outline_title or inputs["title"] or inputs["topic"])
                        generated_any = generate_missing_sections(inputs, title)
                        if generated_any:
                            st.session_state["generation_success_message"] = "Generated all sections."
                        else:
                            st.session_state["generation_success_message"] = "All sections were already generated."
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed while generating sections: {exc}")
            with prepare_col2:
                st.caption("This generates every missing section below in Part 5. Use Revise later for changes.")
    else:
        st.subheader("4. AI-Friendly outline")
        st.caption("This mode now creates the outline first, so you can edit headings and key points before generating the full blog.")

        if st.button("Generate AI-friendly outline", type="primary", use_container_width=True):
            try:
                inputs = current_inputs()
                if not inputs["topic"]:
                    st.error("Please enter a topic first.")
                elif not inputs["keywords"]:
                    suggested_keywords = suggest_seo_keywords(inputs)
                    st.session_state.seo_keyword_suggestions = suggested_keywords
                    st.session_state.selected_seo_keywords = []
                    st.session_state.show_seo_keyword_dialog = True
                    st.rerun()
                else:
                    run_ai_outline_generation()
            except Exception as exc:
                st.error(f"Could not generate AI-friendly outline: {exc}")

        verified = st.session_state.get("verified_evidence", {}) or {}
        if verified.get("verified_points") or verified.get("verified_quotes"):
            with st.expander("Verified evidence available to the AI-friendly draft", expanded=False):
                if verified.get("verified_points"):
                    st.markdown("**Verified points**")
                    for item in verified.get("verified_points", [])[:10]:
                        st.write(f"- {item}")
                if verified.get("verified_quotes"):
                    st.markdown("**Verified quotes**")
                    for item in verified.get("verified_quotes", [])[:6]:
                        st.write(f"- {item}")
                if verified.get("unsupported_points"):
                    st.markdown("**Unsupported or weak points**")
                    for item in verified.get("unsupported_points", [])[:6]:
                        st.write(f"- {item}")

        if st.session_state.ai_outline:
            st.text_input("Final AI-friendly article title", key="ai_outline_title")
            st.caption("You can edit any heading, objective, and key points before generating the full blog.")

            with st.form("add_ai_section_form", clear_on_submit=True):
                add_prompt_col, add_button_col = st.columns([4, 1.2])
                with add_prompt_col:
                    ai_new_section_prompt = st.text_input(
                        "Add section with a one-line prompt",
                        key="ai_new_section_prompt",
                        placeholder="e.g. Add a section answering how teams can measure results",
                    )
                with add_button_col:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    add_ai_section_submitted = st.form_submit_button("Add section", use_container_width=True)

                if add_ai_section_submitted:
                    one_liner = clean_text(ai_new_section_prompt)
                    if not one_liner:
                        st.error("Enter a one-line prompt for the new section.")
                    else:
                        try:
                            new_section = generate_new_ai_section_from_prompt(one_liner)
                        except Exception:
                            new_section = build_manual_section(one_liner)

                        st.session_state.ai_outline.append(new_section)
                        normalise_ai_outline()
                        st.success("Section added.")
                        st.rerun()

            updated_ai_outline: list[dict[str, Any]] = []
            delete_ai_section_id_value: str | None = None
            for idx, section in enumerate(st.session_state.ai_outline):
                with st.expander(f"Section {idx + 1}: {section.get('heading', 'Untitled')}", expanded=(idx == 0)):
                    heading = st.text_input(
                        f"AI heading {idx + 1}",
                        value=clean_text(section.get("heading", "")),
                        key=f"ai_heading_{idx}",
                    )

                    objective_value = clean_text(section.get("objective", ""))
                    objective_height = calc_text_area_height(
                        objective_value,
                        min_height=140,
                        line_px=28,
                        extra_lines=3,
                    )
                    objective = st.text_area(
                        f"AI objective {idx + 1}",
                        value=objective_value,
                        key=f"ai_objective_{idx}",
                        height=objective_height,
                    )

                    key_points_value = to_bullet_lines(section.get("keyPoints", []))
                    key_points_height = calc_text_area_height(
                        key_points_value,
                        min_height=170,
                        line_px=30,
                        extra_lines=3,
                    )
                    key_points_text = st.text_area(
                        f"AI key points {idx + 1}",
                        value=key_points_value,
                        key=f"ai_keypoints_{idx}",
                        height=key_points_height,
                    )

                    section_controls_col1, section_controls_col2 = st.columns([1.2, 1])
                    with section_controls_col1:
                        suggested_words = st.number_input(
                            f"AI suggested words {idx + 1}",
                            min_value=80,
                            max_value=800,
                            value=int(section.get("suggestedWords", 180)),
                            step=20,
                            key=f"ai_words_{idx}",
                        )
                    with section_controls_col2:
                        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                        if st.button("Delete section", key=f"delete_ai_outline_{section['id']}", use_container_width=True):
                            delete_ai_section_id_value = str(section["id"])

                    updated_ai_outline.append(
                        {
                            "id": section.get("id", f"s{idx+1}"),
                            "heading": clean_text(heading),
                            "objective": clean_text(objective),
                            "keyPoints": from_bullet_lines(key_points_text),
                            "suggestedWords": int(suggested_words),
                        }
                    )

            st.session_state.ai_outline = updated_ai_outline
            normalise_ai_outline()

            if delete_ai_section_id_value:
                delete_ai_section(delete_ai_section_id_value)
                st.success("Section deleted.")
                st.rerun()

            generate_blog_col1, generate_blog_col2 = st.columns([1.7, 3])
            with generate_blog_col1:
                if st.button("Generate AI-friendly blog", type="primary", use_container_width=True):
                    try:
                        run_ai_friendly_generation()
                    except Exception as exc:
                        st.error(f"Could not generate AI-friendly blog: {exc}")
            with generate_blog_col2:
                st.caption("This uses the edited AI-friendly outline above to generate one complete blog draft.")

if st.session_state.get("generation_success_message"):
    st.success(st.session_state.pop("generation_success_message"))

if st.session_state.get("revision_success_message"):
    st.success(st.session_state.pop("revision_success_message"))

st.divider()

if st.session_state.blog_mode == "Writer Version":
    st.subheader("5. Generate article sections")

    if st.session_state.outline and st.session_state.sections_workspace_ready:
        inputs = current_inputs()
        title = clean_text(st.session_state.outline_title or inputs["title"] or inputs["topic"])

        top_actions_col1, top_actions_col2 = st.columns([1.5, 4])
        with top_actions_col1:
            if st.button("Generate all missing sections", use_container_width=True):
                try:
                    generated_any = generate_missing_sections(inputs, title)
                    if generated_any:
                        st.success("Generated all missing sections.")
                    else:
                        st.info("No missing sections to generate.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed while generating missing sections: {exc}")
        with top_actions_col2:
            st.caption("Each section now opens as an expandable writing panel with its own generate, revise, and delete controls.")

        delete_section_id_from_workspace: str | None = None
        for idx, section in enumerate(st.session_state.outline):
            key = section["id"]
            content_key = f"content_{key}"
            revision_key = f"rev_inst_{key}"

            if content_key not in st.session_state:
                st.session_state[content_key] = st.session_state.sections_content.get(key, "")

            heading_label = clean_text(section.get("heading", "Untitled section")) or "Untitled section"
            with st.expander(f"Section {idx + 1}: {heading_label}", expanded=(idx == 0)):
                st.caption(section.get("objective", ""))

                if section.get("keyPoints"):
                    st.markdown("**Key points**")
                    st.markdown("\n".join(f"- {clean_text(point)}" for point in section["keyPoints"]))

                meta_col1, meta_col2, meta_col3 = st.columns([1, 1.2, 1])
                with meta_col1:
                    st.caption(f"Suggested words: {int(section.get('suggestedWords', 180))}")
                with meta_col2:
                    if st.button("Generate this section", key=f"generate_{key}", use_container_width=True):
                        try:
                            tighter_section = dict(section)
                            tighter_section["objective"] = (
                                f"{clean_text(section.get('objective', ''))} "
                                f"Write approximately {int(section['suggestedWords'])} words. "
                                f"Do not exceed the target by more than 120 words."
                            ).strip()

                            section_text = clean_text(
                                generate_text(
                                    section_system_prompt(inputs["language"]),
                                    section_user_prompt(inputs, tighter_section, title, st.session_state.outline),
                                    max_tokens=section_max_tokens(int(section["suggestedWords"])),
                                )
                            )
                            st.session_state["pending_generation_update"] = {
                                "section_id": key,
                                "content": section_text,
                            }
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Generation failed: {exc}")
                with meta_col3:
                    if st.button("Delete this section", key=f"delete_workspace_{key}", use_container_width=True):
                        delete_section_id_from_workspace = str(key)

                current_content = st.session_state.get(content_key, "")
                content_height = calc_text_area_height(
                    current_content,
                    min_height=420,
                    line_px=28,
                    extra_lines=10,
                )

                edited = st.text_area(
                    f"Generated content for {heading_label}",
                    key=content_key,
                    height=content_height,
                )
                st.session_state.sections_content[key] = sanitise_section_content(edited, heading_label)

                revision_instruction = st.text_input(
                    f"Revision instruction for {heading_label}",
                    key=revision_key,
                    placeholder="e.g. Make this more conversational and add one stronger example",
                )

                if st.button("Revise this section", key=f"revise_{key}"):
                    try:
                        source_text = clean_text(st.session_state.sections_content.get(key, ""))

                        revised = clean_text(
                            generate_text(
                                revision_system_prompt(inputs["language"]),
                                revision_user_prompt(
                                    section["heading"],
                                    source_text,
                                    revision_instruction,
                                    inputs["language"],
                                ),
                                max_tokens=2200,
                            )
                        )

                        st.session_state["pending_revision_update"] = {
                            "section_id": key,
                            "content": revised,
                        }
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Revision failed: {exc}")

        if delete_section_id_from_workspace:
            delete_section(delete_section_id_from_workspace)
            st.success("Section deleted.")
            st.rerun()

    else:
        if st.session_state.outline:
            st.info("Review the outline, then click 'Generate sections' above to open the section editors here.")
        else:
            st.info("Generate an outline first to create the section editors.")

else:
    st.subheader("5. AI-Friendly full draft")

    if st.session_state.ai_outline and not st.session_state.ai_friendly_draft:
        st.info("Review the AI-friendly outline above, then generate the full blog.")

    if st.session_state.ai_friendly_draft:
        if not st.session_state.ai_friendly_draft_editor:
            st.session_state.ai_friendly_draft_editor = st.session_state.ai_friendly_draft

        draft_height = calc_text_area_height(
            st.session_state.ai_friendly_draft_editor,
            min_height=600,
            line_px=26,
            extra_lines=10,
        )

        edited_draft = st.text_area(
            "Generated AI-friendly blog",
            value=st.session_state.ai_friendly_draft_editor,
            key="ai_friendly_draft_editor_widget",
            height=draft_height,
        )

        st.session_state.ai_friendly_draft_editor = edited_draft
        st.session_state.ai_friendly_draft = edited_draft

        ai_action_col1, ai_action_col2 = st.columns([1.2, 3.8])
        with ai_action_col1:
            if st.button("Regenerate AI-friendly blog", use_container_width=True):
                try:
                    run_ai_friendly_generation()
                except Exception as exc:
                    st.error(f"Regeneration failed: {exc}")
        with ai_action_col2:
            st.caption("You can edit the draft directly in the text area above before exporting.")
    else:
        st.info("Generate the AI-friendly outline first, then generate the full blog.")

st.subheader("6. Export")

if st.session_state.blog_mode == "Writer Version":
    if st.session_state.outline:
        inputs = current_inputs()
        title = clean_text(st.session_state.outline_title or inputs["title"] or inputs["topic"])

        ordered_sections = [
            {
                "heading": section["heading"],
                "content": sanitise_section_content(
                    st.session_state.sections_content.get(section["id"], ""),
                    section["heading"],
                ),
            }
            for section in st.session_state.outline
        ]

        export_sections = build_export_sections_with_appendix(
            ordered_sections,
            inputs["keywords"],
        )

        combined_markdown = "\n\n".join(
            f"## {item['heading']}\n\n{item['content']}"
            for item in export_sections
            if item["content"].strip()
        )

        preview_height = calc_text_area_height(
            combined_markdown,
            min_height=500,
            line_px=26,
            extra_lines=8,
        )

        st.text_area("Combined article preview", value=combined_markdown, height=preview_height)

        export_col1, export_col2 = st.columns(2)

        with export_col1:
            docx_bytes = export_blog_docx(title or "blog-article", export_sections)
            st.download_button(
                "Download DOCX",
                data=docx_bytes,
                file_name="blog-article.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        with export_col2:
            pdf_bytes = export_blog_pdf(title or "blog-article", export_sections)
            st.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name="blog-article.pdf",
                mime="application/pdf",
            )
    else:
        st.info("Generate content first to enable export.")
else:
    if st.session_state.ai_friendly_draft.strip():
        inputs = current_inputs()
        export_title = clean_text(
            st.session_state.ai_outline_title or inputs["title"] or inputs["topic"] or "AI-friendly blog"
        )
        export_sections = markdown_to_export_sections(st.session_state.ai_friendly_draft, export_title)
        export_sections = build_export_sections_with_appendix(export_sections, inputs["keywords"])

        preview_markdown = "\n\n".join(
            f"## {item['heading']}\n\n{item['content']}"
            for item in export_sections
            if item["content"].strip()
        )

        preview_height = calc_text_area_height(
            preview_markdown,
            min_height=500,
            line_px=26,
            extra_lines=8,
        )
        st.text_area("Combined article preview", value=preview_markdown, height=preview_height)

        export_col1, export_col2 = st.columns(2)

        with export_col1:
            docx_bytes = export_blog_docx(export_title or "blog-article", export_sections)
            st.download_button(
                "Download DOCX",
                data=docx_bytes,
                file_name="blog-article.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        with export_col2:
            pdf_bytes = export_blog_pdf(export_title or "blog-article", export_sections)
            st.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name="blog-article.pdf",
                mime="application/pdf",
            )
    else:
        st.info("Generate the AI-friendly draft first to enable export.")
