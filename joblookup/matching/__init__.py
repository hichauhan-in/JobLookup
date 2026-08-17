"""Finding the jobs worth reading, and judging them."""

from __future__ import annotations

from joblookup.matching.dedupe import find_duplicate, is_duplicate, similarity
from joblookup.matching.pipeline import ProfileMissing, run_matching
from joblookup.matching.prefilter import prefilter
from joblookup.matching.recall import recall
from joblookup.matching.rerank import assign_band, composite_score, score_jobs

__all__ = [
    "ProfileMissing",
    "assign_band",
    "composite_score",
    "find_duplicate",
    "is_duplicate",
    "prefilter",
    "recall",
    "run_matching",
    "score_jobs",
    "similarity",
]
