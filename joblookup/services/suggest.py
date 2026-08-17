"""Choosing which companies to watch, and which roles to look for.

Two different problems, deliberately solved two different ways.

Companies are a **factual** question: does this board answer to this name. A
model asked to invent company slugs produces plausible ones that 404, which is
worse than useless because the failure is silent. So the shortlist is ranked
deterministically over a catalogue that was verified against the live APIs.

Roles are a **judgement** question: what could this person credibly do next.
That is exactly what the model is for, so it is asked - and when no model is
available there is a rules-based answer rather than nothing.
"""

from __future__ import annotations

import re
from typing import Any

from joblookup.config import Settings
from joblookup.sources import catalogue
from joblookup.sources.catalogue import Suggestion

#: Words in a profile that mean the same thing as a catalogue tag.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "ai": ("machine learning", "deep learning", "llm", "genai", "nlp", "artificial intelligence"),
    "ml": ("machine learning", "pytorch", "tensorflow", "scikit", "mlops", "model"),
    "data": ("sql", "etl", "warehouse", "analytics", "spark", "airflow", "dbt", "pipeline"),
    "analytics": ("bi", "tableau", "looker", "power bi", "reporting", "dashboards"),
    "backend": ("python", "java", "golang", "go", "node", "ruby", "c#", "api", "microservices"),
    "frontend": ("react", "vue", "angular", "typescript", "javascript", "css", "ui"),
    "mobile": ("ios", "android", "swift", "kotlin", "react native", "flutter"),
    "infrastructure": ("kubernetes", "terraform", "aws", "azure", "gcp", "cloud", "sre"),
    "devops": ("ci/cd", "jenkins", "docker", "platform", "sre", "automation"),
    "security": ("infosec", "appsec", "penetration", "iam", "compliance", "soc"),
    "database": ("postgres", "mysql", "mongodb", "oracle", "sql server"),
    "design": ("figma", "ux", "ui", "product design", "user research", "prototyping"),
    "product": ("product manager", "roadmap", "discovery", "stakeholder"),
    "sales": ("account executive", "business development", "quota", "crm", "pipeline"),
    "marketing": ("seo", "growth", "campaign", "content", "brand", "demand generation"),
    "support": ("customer success", "helpdesk", "service desk", "technical support"),
    "operations": ("supply chain", "logistics", "process", "programme", "program management"),
    "hr": ("recruiting", "talent", "people ops", "human resources"),
    "it-operations": ("it support", "sysadmin", "desktop support", "infrastructure support"),
    "fintech": ("payments", "banking", "trading", "lending", "financial"),
    "healthtech": ("healthcare", "clinical", "patient", "medical", "pharma"),
    "gaming": ("unity", "unreal", "game"),
    "hardware": ("firmware", "embedded", "electronics", "pcb", "asic", "silicon"),
    "developer-tools": ("developer experience", "sdk", "cli", "tooling"),
    "ecommerce": ("retail", "marketplace", "shopify", "commerce"),
    "remote": ("remote",),
    "research": ("research", "phd", "publication"),
}

#: How much each signal is worth. Fit matters most; prestige only breaks ties.
WEIGHT_TAG = 1.0
WEIGHT_TITLE = 1.4
WEIGHT_REGION = 1.2
WEIGHT_TIER = 0.5
WEIGHT_SIZE = 0.4

#: No single board may take more than this share of a shortlist, so a suggestion
#: never turns into "just add forty Greenhouse companies".
BOARD_SHARE = 0.45


def _haystack(profile: dict[str, Any]) -> str:
    parts: list[str] = []
    parts += [str(item) for item in profile.get("target_titles") or []]
    parts += [str(item) for item in profile.get("domains") or []]
    parts.append(str(profile.get("headline") or ""))
    for skill in profile.get("skills") or []:
        parts.append(str(skill.get("name") if isinstance(skill, dict) else skill))
    for role in profile.get("roles") or []:
        if isinstance(role, dict):
            parts.append(str(role.get("title") or ""))
    return " ".join(parts).lower()


def profile_tags(profile: dict[str, Any]) -> set[str]:
    """Which catalogue tags this person's profile actually points at.

    Matched on whole words. Substring matching looked fine until "user research"
    started counting as search experience and "it" matched almost everything.
    """
    text = _haystack(profile)
    if not text.strip():
        return set()
    found = set()
    for tag in catalogue.all_tags():
        needles = {tag, tag.replace("-", " "), *SYNONYMS.get(tag, ())}
        if any(re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text) for needle in needles):
            found.add(tag)
    return found


def _regions_for(profile: dict[str, Any], settings: Settings) -> set[str]:
    """Where this person is looking, as country codes."""
    codes = {settings.search.region} if settings.search.region != "remote" else set()
    places = " ".join(str(item) for item in profile.get("locations") or []).lower()
    for code, names in {
        "us": ("united states", "usa", "america", "new york", "san francisco", "seattle", "austin"),
        "gb": ("united kingdom", "uk", "england", "london", "manchester", "scotland"),
        "in": (
            "india",
            "bangalore",
            "bengaluru",
            "hyderabad",
            "pune",
            "mumbai",
            "delhi",
            "chennai",
        ),
        "de": ("germany", "berlin", "munich", "münchen", "hamburg", "frankfurt"),
        "nl": ("netherlands", "amsterdam", "holland"),
        "fr": ("france", "paris"),
        "ca": ("canada", "toronto", "vancouver", "montreal"),
        "ie": ("ireland", "dublin"),
        "sg": ("singapore",),
        "au": ("australia", "sydney", "melbourne"),
        "es": ("spain", "madrid", "barcelona"),
        "gr": ("greece", "athens"),
        "se": ("sweden", "stockholm"),
        "ae": ("dubai", "abu dhabi", "emirates"),
    }.items():
        if any(name in places for name in names):
            codes.add(code)
    return {code for code in codes if code}


def rank_companies(
    profile: dict[str, Any],
    settings: Settings,
    *,
    limit: int = 100,
    boards: list[str] | None = None,
) -> list[Suggestion]:
    """The catalogue, ordered by how well each company fits this person."""
    tags = profile_tags(profile)
    regions = _regions_for(profile, settings)
    titles = [str(item).lower() for item in profile.get("target_titles") or []]
    remote_wanted = settings.search.remote_only or settings.search.region == "remote"

    biggest = max((company.openings for company in catalogue.COMPANIES), default=1) or 1

    scored: list[Suggestion] = []
    for company in catalogue.COMPANIES:
        if boards and company.board not in boards:
            continue
        reasons: list[str] = []
        score = 0.0

        overlap = tags & set(company.tags)
        if overlap:
            score += WEIGHT_TAG * len(overlap)
            reasons.append("Matches your " + ", ".join(sorted(overlap)[:3]))

        # A target title naming one of the company's tags is a stronger signal
        # than the same word appearing somewhere in a long skills list.
        for title in titles:
            hits = [
                tag
                for tag in company.tags
                if re.search(rf"(?<!\w){re.escape(tag.replace('-', ' '))}(?!\w)", title)
            ]
            if hits:
                score += WEIGHT_TITLE
                reasons.append(f"Fits what you are targeting ({hits[0]})")
                break

        if regions & set(company.regions):
            score += WEIGHT_REGION
            reasons.append("Hires where you are looking")
        elif regions:
            score -= 0.3

        if remote_wanted and "remote" in company.tags:
            score += 0.8
            reasons.append("Remote-friendly")

        score += WEIGHT_TIER * (4 - company.tier)
        if company.tier == 1:
            reasons.append("Pays at the top of the market")

        score += WEIGHT_SIZE * (company.openings / biggest)
        if company.openings >= 300:
            reasons.append(f"{company.openings} openings when last checked")

        scored.append(Suggestion(company=company, score=score, reasons=reasons[:3]))

    scored.sort(key=lambda item: (-item.score, item.company.name))
    return _spread_across_boards(scored, limit)


def _spread_across_boards(ranked: list[Suggestion], limit: int) -> list[Suggestion]:
    """Take the best, but never let one board crowd out the others."""
    cap = max(1, int(limit * BOARD_SHARE))
    chosen: list[Suggestion] = []
    used: dict[str, int] = {}
    overflow: list[Suggestion] = []

    for entry in ranked:
        board = entry.company.board
        if used.get(board, 0) < cap:
            chosen.append(entry)
            used[board] = used.get(board, 0) + 1
        else:
            overflow.append(entry)
        if len(chosen) >= limit:
            return chosen

    # Only once every board has had its share does the best board fill the rest.
    for entry in overflow:
        if len(chosen) >= limit:
            break
        chosen.append(entry)
    return chosen


def grouped_slugs(suggestions: list[Suggestion]) -> dict[str, list[str]]:
    """What each board's 'Companies to watch' box should contain."""
    grouped: dict[str, list[str]] = {}
    for entry in suggestions:
        grouped.setdefault(entry.company.board, []).append(entry.company.slug)
    return grouped


# --- roles --------------------------------------------------------------------
ROLE_SYSTEM = """You suggest job titles a candidate should search for.

Rules:
- Suggest titles that exist in real job adverts, not invented ones.
- Base every suggestion on evidence in the profile. Never assume a skill.
- Include a mix: roles they clearly already qualify for, and one or two that are
  a realistic step up.
- Keep titles short and searchable, as a person would type them into a job site.
- No em dashes anywhere in your output.

Reply with JSON only:
{
  "roles": [
    {"title": "...", "why": "one sentence grounded in their experience",
     "reach": "ready" | "stretch"}
  ]
}"""


def _role_user(profile: dict[str, Any], count: int) -> str:
    from joblookup.prompts import candidate_block

    return (
        f"{candidate_block(profile)}\n\n"
        f"Suggest {count} job titles this person should be searching for. "
        "Order them with the strongest fit first."
    )


def suggest_roles(
    profile: dict[str, Any],
    client: Any | None = None,
    *,
    count: int = 12,
) -> dict[str, Any]:
    """Titles worth searching for, judged from the profile."""
    if not (profile.get("skills") or profile.get("roles") or profile.get("headline")):
        return {
            "roles": [],
            "source": "none",
            "note": "Add a CV on the Profile screen first; there is nothing to work from yet.",
        }

    if client is not None:
        try:
            payload = client.complete_json(ROLE_SYSTEM, _role_user(profile, count))
            roles = [role for role in payload.get("roles") or [] if role.get("title")]
            if roles:
                return {"roles": roles[:count], "source": "model", "note": ""}
        except Exception as exc:  # noqa: BLE001
            return {
                "roles": _roles_from_rules(profile, count),
                "source": "rules",
                "note": (
                    f"The model could not be reached ({exc}), so these come from your CV alone."
                ),
            }

    return {
        "roles": _roles_from_rules(profile, count),
        "source": "rules",
        "note": "No model is configured, so these come from your job titles and skills alone.",
    }


#: Enough to be useful without a model. Deliberately plain.
_LADDER = ("Junior", "", "Senior", "Staff", "Principal", "Lead")


def _roles_from_rules(profile: dict[str, Any], count: int) -> list[dict[str, str]]:
    seniority = str(profile.get("seniority") or "mid").lower()
    seen: dict[str, dict[str, str]] = {}

    def add(title: str, why: str, reach: str) -> None:
        clean = " ".join(title.split())
        if clean and clean.lower() not in seen:
            seen[clean.lower()] = {"title": clean, "why": why, "reach": reach}

    for role in (profile.get("roles") or [])[:4]:
        title = str(role.get("title") or "").strip() if isinstance(role, dict) else ""
        if not title:
            continue
        add(title, "You have held this title before.", "ready")
        bare = title
        for prefix in _LADDER:
            if prefix and bare.lower().startswith(prefix.lower() + " "):
                bare = bare[len(prefix) + 1 :]
        if seniority in ("mid", "senior"):
            add(f"Senior {bare}", "The obvious next step from what you have done.", "stretch")
        if seniority in ("senior", "staff"):
            add(f"Lead {bare}", "A step up, if you want more scope.", "stretch")

    for title in (profile.get("target_titles") or [])[:6]:
        add(str(title), "You said you are looking for this.", "ready")

    return list(seen.values())[:count]
