"""Turning CV text into structured facts.

The model does the reading. Everything it returns is coerced into the expected
shape here rather than trusted, because a hallucinated field type further down
is much harder to trace than a rejected one at the boundary.
"""

from __future__ import annotations

from typing import Any

from joblookup import prompts
from joblookup.config import Settings
from joblookup.llm import LLMClient

LEVELS = ("beginner", "working", "strong", "expert", "unknown")
SENIORITIES = ("intern", "junior", "mid", "senior", "lead", "principal", "director")


def extract(client: LLMClient, text: str, settings: Settings) -> dict[str, Any]:
    raw = client.complete_json(
        prompts.CV_EXTRACT_SYSTEM,
        prompts.cv_extract_user(text, settings.profile.extract_window_chars),
        temperature=0.05,
        max_tokens=4000,
    )
    return coerce(raw if isinstance(raw, dict) else {})


def coerce(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_name": _text(data.get("full_name")),
        "headline": _text(data.get("headline")),
        "location": _text(data.get("location")),
        "email": _text(data.get("email")),
        "phone": _text(data.get("phone")),
        "links": _strings(data.get("links"), 10),
        "summary": _text(data.get("summary"), 1200),
        "total_years_experience": _number(data.get("total_years_experience")),
        "seniority": _choice(data.get("seniority"), SENIORITIES, "mid"),
        "roles": _roles(data.get("roles")),
        "skills": _skills(data.get("skills")),
        "domains": _strings(data.get("domains"), 20),
        "tools": _strings(data.get("tools"), 60),
        "education": _education(data.get("education")),
        "certifications": _strings(data.get("certifications"), 30),
        "languages": _strings(data.get("languages"), 15),
    }


def _text(value: Any, limit: int = 300) -> str:
    return str(value).strip()[:limit] if value is not None else ""


def _number(value: Any) -> float:
    try:
        return max(0.0, min(70.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _choice(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in allowed else fallback


def _strings(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: dict[str, None] = {}
    for item in value:
        text = str(item).strip()
        if text and text.lower() not in {key.lower() for key in seen}:
            seen[text] = None
        if len(seen) >= limit:
            break
    return list(seen)


def _roles(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    roles = []
    for item in value[:25]:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"), 160)
        if not title:
            continue
        roles.append(
            {
                "title": title,
                "company": _text(item.get("company"), 160),
                "start": _text(item.get("start"), 10),
                "end": _text(item.get("end"), 10),
                "current": bool(item.get("current")),
                "summary": _text(item.get("summary"), 800),
                "achievements": _strings(item.get("achievements"), 12),
            }
        )
    return roles


def _skills(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    skills: dict[str, dict[str, Any]] = {}
    for item in value[:200]:
        if isinstance(item, dict):
            name = _text(item.get("name"), 80)
            level = _choice(item.get("level"), LEVELS, "unknown")
            years = _number(item.get("years"))
            category = _text(item.get("category"), 60)
        else:
            name, level, years, category = _text(item, 80), "unknown", 0.0, ""
        if not name:
            continue
        key = name.lower()
        # The same skill listed twice keeps the stronger claim.
        current = skills.get(key)
        if current is None or years > current["years"]:
            skills[key] = {"name": name, "level": level, "years": years, "category": category}
    return list(skills.values())


def _education(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    entries = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue
        degree = _text(item.get("degree"), 200)
        if not degree:
            continue
        entries.append(
            {
                "degree": degree,
                "institution": _text(item.get("institution"), 200),
                "year": _text(item.get("year"), 10),
            }
        )
    return entries
