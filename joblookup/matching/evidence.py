"""Repeatable job relevance with inspectable evidence and explicit uncertainty."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from joblookup.matching.constraints import additional_constraints, priority
from joblookup.matching.eligibility import contains_phrase, location_fit
from joblookup.matching.requirements import (
    IMPORTANCE,
    management_role,
    requirement_context,
    role_family,
)
from joblookup.models import seniority_rank
from joblookup.sources.normalize import age_days, normalize_title

ENGINE_VERSION = "evidence-v2"

SKILLS = {
    "Python": ("python",),
    "JavaScript": ("javascript",),
    "TypeScript": ("typescript",),
    "Java": ("java",),
    "C++": ("c++",),
    "C#": ("c#", "c sharp"),
    ".NET": (".net", "dotnet", "asp.net"),
    "Go": ("golang", "go programming"),
    "Rust": ("rust",),
    "React": ("react", "reactjs", "react.js"),
    "Node.js": ("node.js", "nodejs"),
    "Angular": ("angular",),
    "Vue": ("vue.js", "vuejs", "vue"),
    "SQL": ("sql", "postgresql", "mysql", "sql server"),
    "PostgreSQL": ("postgresql", "postgres"),
    "MongoDB": ("mongodb",),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure",),
    "GCP": ("gcp", "google cloud"),
    "Kubernetes": ("kubernetes", "k8s"),
    "Docker": ("docker",),
    "Terraform": ("terraform",),
    "Linux": ("linux",),
    "PowerShell": ("powershell",),
    "Networking": ("networking", "tcp/ip", "dns", "network troubleshooting"),
    "M365": ("m365", "microsoft 365", "office 365", "o365"),
    "SharePoint": ("sharepoint",),
    "OneDrive": ("onedrive",),
    "Power Automate": ("power automate",),
    "Power Apps": ("power apps", "powerapps"),
    "Power BI": ("power bi", "powerbi"),
    "Excel": ("microsoft excel", "excel"),
    "Tableau": ("tableau",),
    "Data Analytics": ("data analytics", "data analysis"),
    "Machine Learning": ("machine learning",),
    "PyTorch": ("pytorch",),
    "TensorFlow": ("tensorflow",),
    "Spark": ("apache spark", "pyspark"),
    "Salesforce": ("salesforce",),
    "ServiceNow": ("servicenow",),
    "Zendesk": ("zendesk",),
    "Technical Support": ("technical support", "customer troubleshooting"),
    "Incident Management": ("incident management", "incident response"),
    "Figma": ("figma",),
    "UX Research": ("ux research", "user research"),
    "UI Design": ("ui design", "interface design"),
    "Design Systems": ("design systems", "design system"),
    "Product Management": ("product management",),
    "Project Management": ("project management",),
    "Agile": ("agile", "scrum"),
    "Jira": ("jira",),
    "SEO": ("seo", "search engine optimization"),
    "Content Marketing": ("content marketing",),
    "Google Analytics": ("google analytics", "ga4"),
    "Accounting": ("accounting",),
    "Financial Reporting": ("financial reporting",),
    "SAP": ("sap",),
    "Recruitment": ("recruitment", "talent acquisition"),
    "HRIS": ("hris",),
    "Payroll": ("payroll",),
    "Patient Care": ("patient care",),
    "Clinical Research": ("clinical research",),
    "AutoCAD": ("autocad",),
    "SolidWorks": ("solidworks",),
}

_GENERIC_ROLE_WORDS = frozenset(
    [
        "senior",
        "junior",
        "sr",
        "jr",
        "lead",
        "principal",
        "staff",
        "intern",
        "internship",
        "graduate",
        "head",
        "director",
        "engineer",
        "engineering",
        "developer",
        "development",
        "manager",
        "management",
        "specialist",
        "analyst",
        "associate",
        "consultant",
        "officer",
        "executive",
        "expert",
        "professional",
        "ii",
        "iii",
        "iv",
        "the",
        "a",
        "of",
        "and",
        "remote",
        "hybrid",
        "onsite",
        "contract",
        "full",
        "time",
        "part",
        "f",
        "m",
        "d",
        "w",
        "x",
    ]
)
_ROLE_EXPANSIONS = {
    "sre": "site reliability engineer",
    "swe": "software engineer",
    "devops": "platform reliability",
    "frontend": "front end",
    "backend": "back end",
    "fullstack": "full stack",
    "ux": "user experience",
    "ui": "user interface",
    "hr": "human resources",
    "qa": "quality assurance",
}


@lru_cache(maxsize=1024)
def _pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.IGNORECASE)


@lru_cache(maxsize=1024)
def _aliases(name: str) -> tuple[str, ...]:
    for canonical, aliases in SKILLS.items():
        if name.casefold() == canonical.casefold() or name.casefold() in aliases:
            return aliases
    return (name,)


def skill_evidence(text: str, name: str, *, folded: str | None = None) -> str | None:
    evidence = skill_requirement(text, name, folded=folded)
    return evidence["quote"] if evidence else None


def skill_requirement(text: str, name: str, *, folded: str | None = None) -> dict[str, str] | None:
    folded = text.casefold() if folded is None else folded
    best = None
    for alias in _aliases(name):
        if alias.casefold() not in folded:
            continue
        for found in _pattern(alias).finditer(text):
            importance, _ = requirement_context(text, found.start(), found.end())
            if importance == "negated":
                continue
            start = max(0, found.start() - 60)
            end = min(len(text), found.end() + 95)
            if best is None or IMPORTANCE[importance] > IMPORTANCE[best["importance"]]:
                best = {
                    "skill": name,
                    "quote": " ".join(text[start:end].split()),
                    "importance": importance,
                }
            if importance == "required":
                return best
    return best


def skills_from_text(text: str) -> list[dict[str, Any]]:
    folded = text.casefold()
    return [
        {"name": name, "level": "unknown", "evidence": quote, "core": True}
        for name in SKILLS
        if (quote := skill_evidence(text, name, folded=folded))
    ]


@lru_cache(maxsize=2048)
def role_terms(title: str) -> frozenset[str]:
    tokens = re.findall(r"[a-z0-9+#.]+", normalize_title(title).lower())
    expanded = " ".join(_ROLE_EXPANSIONS.get(token, token) for token in tokens)
    return frozenset(token for token in expanded.split() if token not in _GENERIC_ROLE_WORDS)


def role_fit(title: str, targets: list[str]) -> tuple[float, str]:
    if not targets:
        return 0.0, ""
    best = (0.0, "")
    actual = role_terms(title)
    for target in targets:
        if management_role(title) != management_role(target):
            continue
        desired = role_terms(target)
        if desired and actual:
            overlap = len(desired & actual)
            fit = overlap / max(len(desired), len(actual))
        else:
            fit = float(normalize_title(title) == normalize_title(target))
        family = role_family(title)
        if family and family == role_family(target):
            fit = max(fit, 0.8)
        if fit > best[0]:
            best = (fit, target)
    return best


def evaluate_job(
    job: dict[str, Any], profile: dict[str, Any], *, recency_days: int = 14
) -> dict[str, Any]:
    title = str(job.get("title") or "")
    text = title + "\n" + str(job.get("description") or "")
    folded = text.casefold()
    targets = [str(value) for value in profile.get("target_titles") or [] if value]
    skills = [
        str(value.get("name") or "") if isinstance(value, dict) else str(value)
        for value in profile.get("skills") or []
    ]
    skills = list(dict.fromkeys(value.strip() for value in skills if value.strip()))
    matched = [
        evidence for name in skills if (evidence := skill_requirement(text, name, folded=folded))
    ]
    candidate_aliases = {alias.casefold() for name in skills for alias in _aliases(name)}
    mentioned = [
        evidence
        for name, aliases in SKILLS.items()
        if not candidate_aliases.intersection(alias.casefold() for alias in aliases)
        and (evidence := skill_requirement(text, name, folded=folded))
    ]
    blockers: list[str] = []
    warnings: list[str] = []
    criteria: list[dict[str, Any]] = []

    role, target = role_fit(title, targets)
    role_state = "match" if role >= 0.7 else "partial" if role >= 0.34 else "mismatch"
    if not targets:
        role_state = "unknown"
        warnings.append("Add a target role to establish relevance.")
    elif role < 0.34:
        blockers.append("The job title does not match your target roles.")
    criteria.append(
        {
            "key": "role",
            "label": "Role alignment",
            "state": role_state,
            "detail": f"Closest target: {target}." if target else "No matching target role.",
            "points": round(45 * role),
            "maximum": 45,
        }
    )

    matched_weight = sum(IMPORTANCE[entry["importance"]] for entry in matched)
    missing_weight = sum(IMPORTANCE[entry["importance"]] for entry in mentioned)
    coverage = matched_weight / max(0.01, matched_weight + missing_weight)
    if not skills:
        warnings.append("Add skills or a resume to assess the requirements.")
    elif not matched:
        warnings.append("None of your listed skills is explicitly evidenced in this posting.")
    criteria.append(
        {
            "key": "skills",
            "label": "Skills in the posting",
            "state": "match" if coverage >= 0.7 else "partial" if matched else "unknown",
            "detail": f"{len(matched)} skills evidenced; {len(mentioned)} other skills mentioned.",
            "points": round(30 * coverage),
            "maximum": 30,
        }
    )

    geography, detail = location_fit(job, profile.get("locations") or [])
    if geography == "mismatch" and priority(profile, "location") == "required":
        blockers.append(detail)
    elif geography == "unknown" and priority(profile, "location") == "required":
        warnings.append(detail)
    criteria.append(
        {
            "key": "location",
            "label": "Location eligibility",
            "state": geography,
            "detail": detail,
            "points": 10 if geography == "match" else 0,
            "maximum": 10,
        }
    )

    mode = str(job.get("work_mode") or "unknown")
    modes = profile.get("work_modes") or []
    if modes and mode not in modes and priority(profile, "work_mode") != "any":
        if mode == "unknown":
            if priority(profile, "work_mode") == "required":
                warnings.append("The working arrangement is not stated.")
        else:
            detail = f"{mode.title()} work is outside your preferred arrangements."
            if priority(profile, "work_mode") == "required":
                blockers.append(detail)
            else:
                criteria.append(
                    {
                        "key": "work_mode",
                        "label": "Working arrangement",
                        "state": "partial",
                        "detail": detail,
                        "points": -5,
                        "maximum": 0,
                    }
                )
    employment = str(job.get("employment") or "unknown")
    wanted_employment = profile.get("employment_types") or []
    if (
        wanted_employment
        and employment != "unknown"
        and employment not in wanted_employment
        and priority(profile, "employment") != "any"
    ):
        detail = f"{employment.title()} is outside your preferred employment types."
        if priority(profile, "employment") == "required":
            blockers.append(detail)
        else:
            criteria.append(
                {
                    "key": "employment",
                    "label": "Employment type",
                    "state": "partial",
                    "detail": detail,
                    "points": -5,
                    "maximum": 0,
                }
            )

    actual_level = seniority_rank(job.get("seniority"))
    desired_level = seniority_rank(profile.get("seniority"))
    years_required = re.search(
        r"\b(?:minimum(?: of)?|at least|requires?)\s+(\d{1,2})\+?\s+years?\b"
        r"|\b(\d{1,2})\+\s+years?\s+(?:of\s+)?(?:relevant\s+|professional\s+)?experience\b",
        str(job.get("description") or ""),
        re.IGNORECASE,
    )
    if years_required:
        required = int(years_required.group(1) or years_required.group(2))
        available = float(profile.get("total_years_experience") or 0)
        if available and required > available + 1:
            blockers.append(
                f"The posting explicitly asks for {required}+ years; "
                f"your profile lists {available:g}."
            )
        elif not available:
            warnings.append(
                f"The posting asks for {required}+ years; your experience total is not set."
            )
    level_state, level_detail, level_points = "unknown", "Seniority is not stated.", 0
    if actual_level >= 0 and desired_level >= 0:
        gap = actual_level - desired_level
        level_state = "match" if -1 <= gap <= 1 else "mismatch"
        level_detail = (
            f"{job.get('seniority', '').title()} role; your level is {profile.get('seniority')}."
        )
        level_points = 10 if gap == 0 else 7 if level_state == "match" else 0
        if gap > 1 or gap < -2:
            blockers.append("The stated seniority is outside your experience range.")
    criteria.append(
        {
            "key": "experience",
            "label": "Experience level",
            "state": level_state,
            "detail": level_detail,
            "points": level_points,
            "maximum": 10,
        }
    )

    age = age_days(job.get("posted_at"))
    fresh_state = "match"
    if age is None or age < -1:
        warnings.append("The posting date is missing or invalid; freshness is unverified.")
        fresh_state = "unknown"
    elif age > recency_days:
        blockers.append(f"The posting is older than your {recency_days}-day window.")
        fresh_state = "mismatch"
    criteria.append(
        {
            "key": "freshness",
            "label": "Posting date",
            "state": fresh_state,
            "detail": str(job.get("posted_at") or "Not published"),
            "points": 5 if fresh_state == "match" else 0,
            "maximum": 5,
        }
    )
    if len(str(job.get("description") or "")) < 120 or job.get("partial_description"):
        warnings.append("The description is incomplete; review the original posting.")
    for excluded in profile.get("exclusions") or []:
        if contains_phrase(f"{title} {job.get('company') or ''}", str(excluded)):
            blockers.append(f"Matches your exclusion: {excluded}.")

    for constraint in additional_constraints(job, profile):
        mode = priority(profile, constraint["key"])
        if mode == "any" and constraint["key"] != "availability":
            continue
        if constraint["state"] == "mismatch":
            if mode == "required" or constraint["key"] == "availability":
                blockers.append(constraint["detail"])
        elif constraint["state"] == "unknown" and mode == "required":
            warnings.append(constraint["detail"])
        criteria.append(
            constraint
            | {
                "points": -5 if mode == "preferred" and constraint["state"] == "mismatch" else 0,
                "maximum": 0,
                "priority": mode,
            }
        )

    score = max(0, sum(criterion["points"] for criterion in criteria))
    if blockers:
        band = "excluded"
    elif warnings or score < 60:
        band = "review"
    else:
        band = "strong" if score >= 80 else "good"
    if blockers:
        summary = blockers[0]
    elif not matched:
        summary = "Title alignment found; skill evidence still needs review."
    else:
        names = ", ".join(entry["skill"] for entry in matched[:3])
        summary = f"{names} appear in this posting."
    return {
        "engine": ENGINE_VERSION,
        "score": score,
        "band": band,
        "eligible": not blockers,
        "summary": summary,
        "matched_skills": matched,
        "other_skills": [entry["skill"] for entry in mentioned[:12]],
        "requirements": mentioned[:20],
        "criteria": criteria,
        "blockers": blockers,
        "warnings": warnings,
        "target_role": target,
        "method": "Local evidence, not a hiring probability",
    }
