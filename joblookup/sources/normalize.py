"""Turning whatever a source returned into one comparable shape.

Every field here exists because some source gets it wrong: HTML in a
"plain text" description, "Acme Corporation Ltd." and "Acme" as different
employers, "Remote (US)" in the location field rather than the work-mode field,
and eight different date formats.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from joblookup.models import NormalizedJob, RawJob

# --- text --------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_END_RE = re.compile(r"</(p|div|li|ul|ol|h[1-6]|tr|table|section)\s*>", re.IGNORECASE)
_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"<li[^>]*>", re.IGNORECASE)
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"[ \t\u00a0]+")
_BLANK_RE = re.compile(r"\n{3,}")


def clean_text(value: Any) -> str:
    """Flatten HTML into readable plain text without pulling in a parser.

    Job descriptions are the largest thing stored per posting, and they arrive as
    HTML from roughly half the sources. Structure is preserved only where it
    carries meaning — paragraph breaks and bullet points.
    """
    if value is None:
        return ""
    text = str(value)
    if "<" in text and ">" in text:
        text = _SCRIPT_RE.sub(" ", text)
        text = _BREAK_RE.sub("\n", text)
        text = _LIST_ITEM_RE.sub("\n• ", text)
        text = _BLOCK_END_RE.sub("\n", text)
        text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANK_RE.sub("\n\n", text).strip()


def _fold(value: str) -> str:
    """Lowercase, strip accents, collapse punctuation to single spaces."""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    lowered = stripped.lower()
    return re.sub(r"[^a-z0-9+#. ]+", " ", lowered).strip()


# --- company -----------------------------------------------------------------
_LEGAL_SUFFIXES = {
    "inc",
    "inc.",
    "llc",
    "l.l.c",
    "ltd",
    "ltd.",
    "limited",
    "plc",
    "corp",
    "corp.",
    "corporation",
    "co",
    "co.",
    "company",
    "gmbh",
    "ag",
    "sa",
    "s.a",
    "bv",
    "b.v",
    "nv",
    "n.v",
    "pty",
    "pvt",
    "private",
    "oy",
    "ab",
    "as",
    "aps",
    "srl",
    "spa",
    "sarl",
    "kk",
    "kft",
    "sp",
    "zoo",
    "group",
    "holdings",
    "technologies",
    "technology",
    "labs",
    "solutions",
    "services",
    "international",
    "worldwide",
    "global",
}

_COMPANY_NOISE_RE = re.compile(r"\((?:[^)]*)\)|\bthe\b", re.IGNORECASE)


def normalize_company(name: str) -> str:
    """A stable key for "the same employer".

    Suffix stripping stops at the first token so a company genuinely called
    "Group" or "Labs" does not normalise away to nothing.
    """
    folded = _fold(_COMPANY_NOISE_RE.sub(" ", name or ""))
    tokens = [token for token in folded.split() if token]
    while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


# --- title -------------------------------------------------------------------
_TITLE_NOISE_RE = re.compile(
    r"\b(m/f/d|f/m/d|m/w/d|w/m/d|h/f|all genders|any gender|remote|hybrid|onsite|on-site|"
    r"full[- ]time|part[- ]time|contract|permanent|urgent|hiring|we are hiring|new)\b",
    re.IGNORECASE,
)
_BRACKET_RE = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_SEPARATOR_RE = re.compile(r"\s*[-–—|/,]\s*")

# Common ways of saying the same job. Only pairs that are genuinely the same
# role belong here — merging "engineer" and "manager" would hide real openings.
_TITLE_SYNONYMS = {
    "sr": "senior",
    "snr": "senior",
    "jr": "junior",
    "jnr": "junior",
    "sw": "software",
    "swe": "software engineer",
    "dev": "developer",
    "engineer ii": "engineer",
    "engineer i": "engineer",
    "engineer iii": "engineer",
    "sre": "site reliability engineer",
    "devops": "dev ops",
    "qa": "quality assurance",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "pm": "product manager",
    "sdet": "software development engineer in test",
}


def normalize_title(title: str) -> str:
    text = _BRACKET_RE.sub(" ", title or "")
    text = _TITLE_NOISE_RE.sub(" ", text)
    text = _SEPARATOR_RE.sub(" ", text)
    # Trailing full stops survive folding ("node.js" needs the inner one kept),
    # and "Sr." has to reach the synonym table as "sr".
    tokens = [token.strip(".") for token in _fold(text).split()]
    expanded = [_TITLE_SYNONYMS.get(token, token) for token in tokens if token]
    return " ".join(" ".join(expanded).split())


# --- location ----------------------------------------------------------------
_REMOTE_HINTS = ("remote", "anywhere", "work from home", "wfh", "distributed", "telecommute")
_HYBRID_HINTS = ("hybrid", "flexible location", "partially remote", "2 days in office")
_ONSITE_HINTS = ("on-site", "onsite", "in office", "in-office")

_COUNTRY_ALIASES = {
    "usa": "United States",
    "us": "United States",
    "u.s.": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "uae": "United Arab Emirates",
    "deutschland": "Germany",
    "nederland": "Netherlands",
    "holland": "Netherlands",
    "bharat": "India",
}


def normalize_location(location: str) -> tuple[str, str]:
    """Return ``(normalised_key, country)``.

    The key is only used for deciding whether two postings are the same job, so
    it deliberately loses detail that varies between sources.
    """
    raw = clean_text(location)
    if not raw:
        return "", ""
    parts = [part.strip() for part in re.split(r"[,;|/]", raw) if part.strip()]
    country = ""
    if parts:
        tail = parts[-1].strip().rstrip(".")
        country = _COUNTRY_ALIASES.get(tail.lower(), tail if len(tail) > 2 else "")
        if len(tail) == 2 and tail.isupper():
            # Two-letter tails are US/CA state codes far more often than countries.
            country = ""
    key = _fold(" ".join(parts[:2]))
    return key, country


def detect_work_mode(*, title: str, location: str, description: str, given: str = "") -> str:
    if given:
        lowered = given.strip().lower()
        if lowered in {"remote", "hybrid", "onsite", "on-site", "on_site"}:
            return "onsite" if lowered.startswith("on") else lowered
    haystack = f"{title} {location} {description[:1500]}".lower()
    if any(hint in haystack for hint in _HYBRID_HINTS):
        return "hybrid"
    if any(hint in haystack for hint in _REMOTE_HINTS):
        return "remote"
    if any(hint in haystack for hint in _ONSITE_HINTS):
        return "onsite"
    return "unknown"


_EMPLOYMENT_HINTS = (
    ("internship", ("intern", "internship", "praktikum", "working student", "werkstudent")),
    ("contract", ("contract", "contractor", "freelance", "b2b", "fixed term", "fixed-term")),
    ("part-time", ("part time", "part-time", "teilzeit")),
    ("temporary", ("temporary", "temp ", "seasonal")),
    ("full-time", ("full time", "full-time", "permanent", "vollzeit")),
)


def detect_employment(*, title: str, description: str, given: str = "") -> str:
    if given:
        folded = given.strip().lower().replace("_", " ").replace("time", " time")
        for canonical, _ in _EMPLOYMENT_HINTS:
            if canonical.replace("-", " ") in folded:
                return canonical
    haystack = f"{title} {description[:1200]}".lower()
    for canonical, hints in _EMPLOYMENT_HINTS:
        if any(hint in haystack for hint in hints):
            return canonical
    return "unknown"


# Order matters: "senior principal engineer" should land on principal, and
# "senior" must be checked before the bare "engineer" default.
_SENIORITY_HINTS = (
    ("director", ("director", "vp ", "vice president", "head of", "chief")),
    ("principal", ("principal", "distinguished", "fellow", "architect", "staff ")),
    ("lead", ("lead", "manager", "supervisor", "team lead", "tech lead")),
    ("senior", ("senior", "sr.", "sr ", " iii", " iv", "expert", "specialist ii")),
    (
        "junior",
        ("junior", "jr.", "jr ", "graduate", "entry level", "entry-level", "associate", " i "),
    ),
    ("intern", ("intern", "internship", "trainee", "apprentice", "working student")),
)


def detect_seniority(title: str, description: str = "") -> str:
    lowered = f" {title.lower()} "
    for canonical, hints in _SENIORITY_HINTS:
        if any(hint in lowered for hint in hints):
            return canonical
    years = re.search(r"(\d+)\+?\s*years?", description[:2000], re.IGNORECASE)
    if years:
        value = int(years.group(1))
        if value >= 8:
            return "senior"
        if value >= 4:
            return "mid"
        if value >= 1:
            return "junior"
    return "mid"


# --- dates -------------------------------------------------------------------
_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%b %d, %Y",
    "%d %b %Y",
    # RFC 822, as used by RSS feeds, with a named zone or a numeric offset.
    "%a, %d %b %Y %H:%M:%S %Z",
    "%a, %d %b %Y %H:%M:%S %z",
)
_RELATIVE_RE = re.compile(r"(\d+)\s*(minute|hour|day|week|month)s?\s*ago", re.IGNORECASE)


def parse_date(value: Any) -> str | None:
    """Best-effort ISO 8601 UTC string, or ``None``.

    A wrong date is worse than no date: the recency filter would either hide a
    fresh posting or surface a stale one, so anything unparseable stays null.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        # Epoch seconds or milliseconds; both appear in the wild.
        seconds = float(value) / 1000.0 if float(value) > 4_000_000_000 else float(value)
        try:
            return (
                datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=0).isoformat()
            )
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    if (match := _RELATIVE_RE.search(text)) is not None:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        delta = {
            "minute": timedelta(minutes=amount),
            "hour": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "week": timedelta(weeks=amount),
            "month": timedelta(days=30 * amount),
        }[unit]
        return (datetime.now(timezone.utc) - delta).replace(microsecond=0).isoformat()

    if re.fullmatch(r"\d{10}|\d{13}", text):
        return parse_date(int(text))

    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = None
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def age_days(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        posted = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - posted).total_seconds() / 86400.0


# --- salary ------------------------------------------------------------------
_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY", "₽": "RUB"}
#: Matches "$90,000 - $120,000", "60k - 80k" and "EUR 70 000 to 90 000".
#: The number is allowed to be short because "60k" is two digits; a range with
#: no thousands marker and no k suffix is rejected below instead.
_SALARY_RE = re.compile(
    r"([$€£₹¥]|\b(?:USD|EUR|GBP|INR|CAD|AUD|CHF|SEK|PLN|SGD)\b)?\s*"
    r"(\d[\d,. ]*\d|\d)\s*([kK])?\s*(?:-|–|to)\s*"
    r"([$€£₹¥])?\s*(\d[\d,. ]*\d|\d)\s*([kK])?",
)


def parse_salary(text: str) -> tuple[float | None, float | None, str]:
    if not text:
        return None, None, ""
    match = _SALARY_RE.search(text[:600])
    if not match:
        return None, None, ""
    symbol = match.group(1) or match.group(4) or ""
    currency = _CURRENCY_SYMBOLS.get(symbol, symbol.upper() if symbol else "")

    def to_number(raw: str, thousand_marker: str | None) -> float | None:
        cleaned = re.sub(r"[,\s]", "", raw).rstrip(".")
        try:
            value = float(cleaned)
        except ValueError:
            return None
        return value * 1000 if thousand_marker else value

    low = to_number(match.group(2), match.group(3))
    high = to_number(match.group(5), match.group(6))
    if low and high and low > high:
        low, high = high, low
    # "5 to 8 years of experience" is not a salary. Anything this small without a
    # k suffix is some other number that happened to sit in a range.
    if (high or 0) < 1000:
        return None, None, ""
    return low, high, currency


# --- fingerprint -------------------------------------------------------------
def fingerprint(company_norm: str, title_norm: str, location_norm: str, *, strict: bool) -> str:
    """The identity of a posting across sources.

    Location is part of the key when ``strict`` is set, which is what keeps
    "Support Engineer, Dublin" and "Support Engineer, Austin" as two separate
    openings rather than one card with two links.
    """
    parts = [company_norm, title_norm, location_norm if strict else ""]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


# --- the whole thing ---------------------------------------------------------
def normalize(raw: RawJob, *, strict_location: bool = True) -> NormalizedJob:
    title = clean_text(raw.title)[:300]
    company = clean_text(raw.company)[:200]
    location = clean_text(raw.location)[:200]
    description = clean_text(raw.description)

    company_norm = normalize_company(company)
    title_norm = normalize_title(title)
    location_norm, country = normalize_location(location)

    salary_min, salary_max, currency = raw.salary_min, raw.salary_max, raw.salary_currency
    salary_period = str(raw.salary_period or raw.raw.get("salary_period") or "").lower()
    if salary_period not in {"hour", "day", "week", "month", "year"}:
        unit = re.search(
            r"(?:\d[\d,.]*\s*[kKmM]?\s*(?:USD|INR|EUR|GBP)?\s*"
            r"(?:/|per\s+)(hour|day|week|month|year)|\b(per annum|annually|LPA)\b)",
            description,
            re.I,
        )
        salary_period = (unit.group(1) or "year").lower() if unit else ""
    if salary_min is None and salary_max is None:
        salary_min, salary_max, currency = parse_salary(f"{title}\n{description[:600]}")

    return NormalizedJob(
        fingerprint=fingerprint(company_norm, title_norm, location_norm, strict=strict_location),
        title=title,
        title_norm=title_norm,
        company=company,
        company_norm=company_norm,
        location=location,
        location_norm=location_norm,
        country=country,
        work_mode=detect_work_mode(
            title=title, location=location, description=description, given=raw.work_mode
        ),
        employment=detect_employment(title=title, description=description, given=raw.employment),
        seniority=detect_seniority(title, description),
        description=description,
        url=(raw.url or "").strip(),
        apply_url=(raw.apply_url or "").strip(),
        posted_at=parse_date(raw.posted_at),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=currency or "",
        salary_period=salary_period,
        source_key=raw.source_key,
        source_job_id=str(raw.source_job_id or ""),
        raw=raw.raw,
    )
