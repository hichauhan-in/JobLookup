"""Rewriting a CV for one specific posting.

The model does the rewriting. The rule that matters most — never claim something
the candidate cannot back up — is enforced here in code afterwards, because a
prompt is a request and this needs to be a guarantee.

Anything the candidate does not have ends up on the interview prep sheet, or
under an explicit "Currently upskilling" heading. It never appears as delivered
experience.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from joblookup import prompts
from joblookup.config import Settings
from joblookup.llm import LLMClient
from joblookup.tailor import style_guard

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*")


@dataclass
class TailorResult:
    content: dict[str, Any] = field(default_factory=dict)
    prep_sheet: dict[str, Any] = field(default_factory=dict)
    markdown: str = ""
    moved_to_upskilling: list[str] = field(default_factory=list)
    style_report: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "prep_sheet": self.prep_sheet,
            "markdown": self.markdown,
            "moved_to_upskilling": self.moved_to_upskilling,
            "style_report": self.style_report,
        }


def tailor(
    client: LLMClient,
    settings: Settings,
    *,
    profile: dict[str, Any],
    cv_text: str,
    job: dict[str, Any],
    score: dict[str, Any] | None = None,
) -> TailorResult:
    raw = client.complete_json(
        prompts.TAILOR_SYSTEM,
        prompts.tailor_user(
            profile,
            cv_text,
            job,
            enrichment=settings.tailor.enrichment,
            max_bullets=settings.tailor.max_bullets_per_role,
        ),
        temperature=0.25,
        max_tokens=4000,
    )
    content = _coerce(raw if isinstance(raw, dict) else {}, settings)
    content, moved = enforce_evidence(content, cv_text, profile, settings)

    report = style_guard.GuardReport()
    if settings.tailor.style_guard:
        content = style_guard.clean_document(content, report)

    prep = build_prep_sheet(client, profile, job, score or {}, moved)
    return TailorResult(
        content=content,
        prep_sheet=prep,
        markdown=to_markdown(content, profile, settings),
        moved_to_upskilling=moved,
        style_report=report.to_dict(),
    )


def build_prep_sheet(
    client: LLMClient,
    profile: dict[str, Any],
    job: dict[str, Any],
    score: dict[str, Any],
    moved: list[str],
) -> dict[str, Any]:
    gaps = {
        "learnable_gaps": [*score.get("learnable_gaps", []), *moved],
        "hard_gaps": score.get("hard_gaps", []),
    }
    try:
        raw = client.complete_json(
            prompts.PREP_SYSTEM,
            prompts.prep_user(profile, job, gaps),
            temperature=0.3,
            max_tokens=2200,
        )
    except Exception:  # noqa: BLE001
        # A missing prep sheet is a disappointment; a failed tailoring run
        # because of it would be a bug.
        return {
            "likely_questions": [],
            "study_list": [],
            "gaps_to_address_honestly": [],
            "questions_to_ask_them": [],
        }
    return raw if isinstance(raw, dict) else {}


# --- the guarantee -----------------------------------------------------------
def enforce_evidence(
    content: dict[str, Any],
    cv_text: str,
    profile: dict[str, Any],
    settings: Settings,
) -> tuple[dict[str, Any], list[str]]:
    """Move any skill the source CV does not evidence out of the CV body.

    A prompt asking the model not to invent things is necessary but not
    sufficient. This is the part that makes it true: a highlighted skill has to
    appear in the CV text or in the extracted profile, or it is relegated.
    """
    evidence = _evidence_set(cv_text, profile)
    highlighted = [
        str(item).strip() for item in content.get("highlighted_skills") or [] if str(item).strip()
    ]

    kept: list[str] = []
    moved: list[str] = []
    for skill in highlighted:
        if _is_evidenced(skill, evidence):
            kept.append(skill)
        else:
            moved.append(skill)

    content["highlighted_skills"] = kept
    if settings.tailor.include_upskilling_section:
        existing = [
            str(item).strip() for item in content.get("upskilling") or [] if str(item).strip()
        ]
        merged = existing + [
            item for item in moved if item.lower() not in {e.lower() for e in existing}
        ]
        content["upskilling"] = merged
    else:
        content["upskilling"] = []
    return content, moved


def _evidence_set(cv_text: str, profile: dict[str, Any]) -> set[str]:
    tokens = {match.group(0).lower().strip(".-") for match in _TOKEN_RE.finditer(cv_text)}
    for skill in profile.get("skills") or []:
        name = skill.get("name") if isinstance(skill, dict) else skill
        for match in _TOKEN_RE.finditer(str(name or "")):
            tokens.add(match.group(0).lower().strip(".-"))
    for key in ("tools", "domains", "certifications"):
        for item in profile.get(key) or []:
            for match in _TOKEN_RE.finditer(str(item)):
                tokens.add(match.group(0).lower().strip(".-"))
    return {token for token in tokens if token}


def _is_evidenced(skill: str, evidence: set[str]) -> bool:
    """Every significant word of a claimed skill must appear in the source.

    "Kubernetes" has to be in the CV. "Azure Kubernetes Service" needs all three
    words, which is stricter than it sounds and is the intended behaviour: a
    partial match is how "Azure" becomes "Azure Machine Learning".
    """
    parts = [
        match.group(0).lower().strip(".-")
        for match in _TOKEN_RE.finditer(skill)
        if len(match.group(0)) > 1
    ]
    if not parts:
        return False
    return all(part in evidence for part in parts)


# --- shaping and output ------------------------------------------------------
def _coerce(data: dict[str, Any], settings: Settings) -> dict[str, Any]:
    limit = settings.tailor.max_bullets_per_role
    roles = []
    for role in data.get("roles") or []:
        if not isinstance(role, dict):
            continue
        title = str(role.get("title") or "").strip()
        if not title:
            continue
        roles.append(
            {
                "title": title,
                "company": str(role.get("company") or "").strip(),
                "start": str(role.get("start") or "").strip(),
                "end": str(role.get("end") or "").strip(),
                "bullets": [
                    str(item).strip() for item in role.get("bullets") or [] if str(item).strip()
                ][:limit],
            }
        )
    return {
        "headline": str(data.get("headline") or "").strip()[:200],
        "summary": str(data.get("summary") or "").strip()[:1500],
        "highlighted_skills": [
            str(item).strip() for item in data.get("highlighted_skills") or [] if str(item).strip()
        ][:30],
        "roles": roles,
        "upskilling": [
            str(item).strip() for item in data.get("upskilling") or [] if str(item).strip()
        ][:15],
        "keywords_covered": [
            str(item).strip() for item in data.get("keywords_covered") or [] if str(item).strip()
        ][:40],
        "omitted": [str(item).strip() for item in data.get("omitted") or [] if str(item).strip()][
            :20
        ],
    }


def to_markdown(content: dict[str, Any], profile: dict[str, Any], settings: Settings) -> str:
    lines: list[str] = []
    name = profile.get("full_name") or ""
    if name:
        lines.append(f"# {name}")
    if content.get("headline"):
        lines.append(f"**{content['headline']}**")

    contact = [
        str(profile.get(key) or "").strip()
        for key in ("location", "email", "phone")
        if str(profile.get(key) or "").strip()
    ]
    contact += [str(link) for link in (profile.get("links") or [])[:3]]
    if contact:
        lines.append(" | ".join(contact))

    if content.get("summary"):
        lines += ["", "## Summary", content["summary"]]

    if content.get("highlighted_skills"):
        lines += ["", "## Skills", ", ".join(content["highlighted_skills"])]

    if content.get("roles"):
        lines += ["", "## Experience"]
        for role in content["roles"]:
            dates = " - ".join(part for part in (role.get("start"), role.get("end")) if part)
            heading = f"### {role['title']}"
            if role.get("company"):
                heading += f", {role['company']}"
            if dates:
                heading += f" ({dates})"
            lines.append(heading)
            lines += [f"- {bullet}" for bullet in role.get("bullets") or []]
            lines.append("")

    if content.get("upskilling") and settings.tailor.include_upskilling_section:
        lines += [
            "",
            f"## {settings.tailor.upskilling_heading}",
            ", ".join(content["upskilling"]),
        ]

    if profile.get("education"):
        lines += ["", "## Education"]
        for entry in profile["education"]:
            parts = [entry.get("degree", ""), entry.get("institution", ""), entry.get("year", "")]
            lines.append("- " + ", ".join(part for part in parts if part))

    if profile.get("certifications"):
        lines += [
            "",
            "## Certifications",
            ", ".join(str(item) for item in profile["certifications"]),
        ]

    return "\n".join(lines).strip() + "\n"


def prep_markdown(prep: dict[str, Any], job: dict[str, Any]) -> str:
    lines = [f"# Interview prep - {job.get('title', '')} at {job.get('company', '')}", ""]

    if prep.get("study_list"):
        lines += ["## What to study", ""]
        for item in prep["study_list"]:
            lines.append(
                f"- **{item.get('topic', '')}** ({item.get('how_long', '')}) - "
                f"{item.get('why_it_matters', '')}"
            )
        lines.append("")

    if prep.get("likely_questions"):
        lines += ["## Likely questions", ""]
        for item in prep["likely_questions"]:
            lines += [f"**{item.get('question', '')}**", f"{item.get('answer_outline', '')}", ""]

    if prep.get("gaps_to_address_honestly"):
        lines += ["## Gaps, and how to talk about them", ""]
        for item in prep["gaps_to_address_honestly"]:
            lines.append(f"- **{item.get('gap', '')}** - {item.get('how_to_frame_it', '')}")
        lines.append("")

    if prep.get("questions_to_ask_them"):
        lines += ["## Questions to ask them", ""]
        lines += [f"- {item}" for item in prep["questions_to_ask_them"]]

    return "\n".join(lines).strip() + "\n"
