"""Conservative, explicit geographic eligibility without model guesses."""

from __future__ import annotations

import re
from typing import Any

COUNTRY_NAMES = {
    "IN": (
        "india",
        "bharat",
        "bengaluru",
        "bangalore",
        "hyderabad",
        "pune",
        "mumbai",
        "delhi",
        "noida",
        "gurugram",
        "gurgaon",
        "chennai",
    ),
    "US": ("united states", "usa", "u.s.", "new york", "san francisco", "seattle", "boston"),
    "GB": ("united kingdom", "uk", "great britain", "england", "london", "scotland"),
    "CA": ("canada", "toronto", "vancouver", "montreal"),
    "DE": ("germany", "deutschland", "berlin", "munich", "hamburg"),
    "NL": ("netherlands", "nederland", "amsterdam", "rotterdam"),
    "FR": ("france", "paris", "lyon"),
    "IE": ("ireland", "dublin"),
    "AU": ("australia", "sydney", "melbourne"),
    "NZ": ("new zealand", "auckland", "wellington"),
    "SG": ("singapore",),
    "AE": ("united arab emirates", "uae", "dubai", "abu dhabi"),
}

CITY_NAMES = (
    ("bengaluru", "bangalore"),
    ("hyderabad",),
    ("pune",),
    ("mumbai",),
    ("delhi", "new delhi"),
    ("noida",),
    ("gurugram", "gurgaon"),
    ("chennai",),
    ("london",),
    ("dublin",),
    ("berlin",),
    ("munich",),
    ("hamburg",),
    ("toronto",),
    ("vancouver",),
    ("montreal",),
    ("sydney",),
    ("melbourne",),
    ("new york",),
    ("san francisco",),
    ("seattle",),
    ("boston",),
    ("paris",),
    ("amsterdam",),
    ("rotterdam",),
    ("dubai",),
    ("abu dhabi",),
)


def contains_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.strip()
    if not phrase or phrase.casefold() not in text.casefold():
        return False
    return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.IGNORECASE))


def countries_in(text: str) -> set[str]:
    clean = str(text or "").strip()
    if clean.upper() in COUNTRY_NAMES:
        return {clean.upper()}
    result = {
        code
        for code, names in COUNTRY_NAMES.items()
        if any(contains_phrase(clean, name) for name in names)
    }
    if re.search(r"\bUS\b", clean):
        result.add("US")
    return result


def location_fit(job: dict[str, Any], targets: list[str]) -> tuple[str, str]:
    if not targets:
        return "unknown", "No preferred location set."
    target_countries = set().union(*(countries_in(target) for target in targets))
    location = str(job.get("location") or "")
    job_countries = countries_in(str(job.get("country") or "")) | countries_in(location)
    if job.get("work_mode") in {"onsite", "hybrid"}:
        requested_cities = {
            names[0]
            for names in CITY_NAMES
            if any(contains_phrase(target, name) for name in names for target in targets)
        }
        listed_cities = {
            names[0]
            for names in CITY_NAMES
            if any(contains_phrase(location, name) for name in names)
        }
        country_wide = any(
            countries_in(target)
            and not any(contains_phrase(target, name) for names in CITY_NAMES for name in names)
            for target in targets
        )
        if (
            requested_cities
            and listed_cities
            and not country_wide
            and not requested_cities.intersection(listed_cities)
        ):
            return (
                "mismatch",
                f"This {job['work_mode']} role is based in {location}, "
                "outside your preferred cities.",
            )
    if target_countries and job_countries:
        if not target_countries.intersection(job_countries):
            return (
                "mismatch",
                f"Listed for {location or job.get('country')}, outside your locations.",
            )
        return "match", f"Listed in your preferred country: {location or job.get('country')}."
    if job.get("work_mode") == "remote" and any(
        contains_phrase(location, word) for word in ("worldwide", "anywhere", "global")
    ):
        return "match", "The posting explicitly accepts worldwide remote applicants."
    if location and any(contains_phrase(location, target) for target in targets):
        return "match", f"Location matches {location}."
    return "unknown", "Location eligibility needs confirmation; remote does not imply worldwide."
