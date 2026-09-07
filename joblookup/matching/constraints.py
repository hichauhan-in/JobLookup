"""Explicit eligibility constraints, separate from relevance scoring."""

from __future__ import annotations

import re
from typing import Any

from joblookup.matching.eligibility import contains_phrase, countries_in


def priority(profile: dict[str, Any], key: str) -> str:
    return (profile.get("constraint_modes") or {}).get(key, "required")


def additional_constraints(job: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    text = str(job.get("description") or "")

    def add(key: str, label: str, state: str, detail: str) -> None:
        rows.append({"key": key, "label": label, "state": state, "detail": detail})

    minimum = float(profile.get("min_salary") or 0)
    if minimum > 0:
        currency = str(job.get("salary_currency") or "").upper()
        desired_currency = str(profile.get("salary_currency") or "").upper()
        period = job.get("salary_period") or (job.get("raw") or {}).get("salary_period")
        wanted_period = profile.get("salary_period") or "year"
        maximum = job.get("salary_max")
        lower = job.get("salary_min")
        if maximum is None and lower is not None and float(lower) >= minimum:
            maximum = lower
        if not maximum or not currency or currency != desired_currency or period != wanted_period:
            add(
                "salary",
                "Compensation",
                "unknown",
                "Pay is missing or uses a different currency or period; no conversion assumed.",
            )
        else:
            state = "match" if float(maximum) >= minimum else "mismatch"
            add(
                "salary",
                "Compensation",
                state,
                f"Published pay reaches {float(maximum):g} {currency}/{period}; "
                f"your minimum is {minimum:g}.",
            )

    if profile.get("needs_sponsorship"):
        refused = re.search(
            r"\b(?:no (?:visa )?sponsorship|(?:cannot|can't|unable to|will not|do not|does not) "
            r"(?:offer |provide )?sponsor|sponsorship (?:is )?not "
            r"(?:available|provided|offered))\b",
            text,
            re.I,
        )
        offered = re.search(
            r"\b(?:(?:visa )?sponsorship (?:is )?(?:available|provided|offered)|"
            r"(?:will|can) sponsor (?:a |your |work )?visa)\b",
            text,
            re.I,
        )
        state = "mismatch" if refused else "match" if offered else "unknown"
        add(
            "sponsorship",
            "Visa sponsorship",
            state,
            "The posting explicitly excludes sponsorship."
            if refused
            else "The posting explicitly offers visa sponsorship."
            if offered
            else "Visa sponsorship is not confirmed in the posting.",
        )

    authorized = profile.get("authorized_countries") or []
    if authorized and not profile.get("needs_sponsorship"):
        restriction = re.search(
            r"\b(?:must be|already|currently) (?:legally )?authori[sz]ed to work in "
            r"(?:the )?([^.;\n]+)",
            text,
            re.I,
        )
        if restriction:
            listed = countries_in(restriction.group(1))
            available = set().union(*(countries_in(country) for country in authorized))
            state = (
                "match" if listed & available else "mismatch" if listed and available else "unknown"
            )
            add("sponsorship", "Work authorization", state, restriction.group(0))

    desired_zone = str(profile.get("timezone_requirement") or "").strip()
    if desired_zone:
        state = "match" if contains_phrase(text, desired_zone) else "unknown"
        add(
            "timezone",
            "Working hours",
            state,
            f"Posting mentions {desired_zone}."
            if state == "match"
            else f"Working-hour compatibility with {desired_zone} needs confirmation.",
        )

    qualifications = profile.get("required_keywords") or []
    if qualifications:
        absent = [value for value in qualifications if not contains_phrase(text, value)]
        add(
            "qualifications",
            "Required posting criteria",
            "unknown" if absent else "match",
            f"Not evidenced: {', '.join(absent)}."
            if absent
            else "All requested posting criteria are explicitly mentioned.",
        )
    if job.get("availability") == "closed":
        add(
            "availability",
            "Application availability",
            "mismatch",
            "The original posting was confirmed closed at the last check.",
        )
    return rows
