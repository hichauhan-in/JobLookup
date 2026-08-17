"""Deciding when two postings are the same job.

The failure modes point in opposite directions and both are bad:

* Merge too eagerly and "Support Engineer, Dublin" swallows "Support Engineer,
  Austin" — two real openings become one, and one of them is invisible.
* Merge too timidly and the same role found on five portals fills the screen
  five times, which is exactly the noise this tool exists to remove.

So the fingerprint is strict (company + title + location) and near-duplicate
detection is a second, narrower pass on top of it.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from joblookup.config import DedupeConfig
from joblookup.models import NormalizedJob

try:  # rapidfuzz is a small optional speed-up, not a requirement.
    from rapidfuzz.fuzz import token_sort_ratio as _ratio

    def similarity(left: str, right: str) -> float:
        return _ratio(left, right) / 100.0

except ImportError:  # pragma: no cover - exercised only without the extra

    def similarity(left: str, right: str) -> float:
        """Token-order-insensitive similarity, close enough to rapidfuzz."""
        if not left or not right:
            return 0.0
        a = " ".join(sorted(left.split()))
        b = " ".join(sorted(right.split()))
        return SequenceMatcher(None, a, b).ratio()


#: Words that change which job a posting is, not merely how it is written.
#: If two titles differ on one of these, they are different openings even when
#: the rest of the string matches.
DISCRIMINATORS = frozenset(
    {
        "intern",
        "junior",
        "senior",
        "lead",
        "principal",
        "staff",
        "director",
        "manager",
        "head",
        "graduate",
        "apprentice",
        "trainee",
        "frontend",
        "backend",
        "fullstack",
        "mobile",
        "ios",
        "android",
        "i",
        "ii",
        "iii",
        "iv",
    }
)


def _discriminating_tokens(title_norm: str) -> frozenset[str]:
    return frozenset(token for token in title_norm.split() if token in DISCRIMINATORS)


def is_duplicate(candidate: NormalizedJob, existing: dict[str, str], config: DedupeConfig) -> bool:
    """True when ``candidate`` is the posting already stored as ``existing``.

    ``existing`` comes from the database and carries ``title_norm``,
    ``location_norm`` and ``description``.
    """
    if _discriminating_tokens(candidate.title_norm) != _discriminating_tokens(
        existing.get("title_norm", "")
    ):
        return False

    if config.require_same_location:
        left = candidate.location_norm
        right = existing.get("location_norm", "")
        # An empty location on either side is missing data, not a mismatch.
        if left and right and left != right and similarity(left, right) < 0.8:
            return False

    if similarity(candidate.title_norm, existing.get("title_norm", "")) >= config.title_similarity:
        return True

    # Some employers post the same job under two different titles. Identical
    # description text is the giveaway, so it gets its own much stricter check.
    left_body = candidate.description[:2000]
    right_body = (existing.get("description") or "")[:2000]
    if len(left_body) > 400 and len(right_body) > 400:
        return similarity(left_body, right_body) >= config.description_similarity
    return False


def find_duplicate(
    candidate: NormalizedJob, existing_rows: list[dict], config: DedupeConfig
) -> int | None:
    """The id of the posting ``candidate`` duplicates, if any."""
    for row in existing_rows:
        if is_duplicate(candidate, row, config):
            return int(row["id"])
    return None
