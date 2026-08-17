"""Stage one: narrowing thousands of postings to the few hundred worth judging.

Two strategies, and the choice is made for you:

**Lexical (always available).** SQLite's FTS5 index over the postings, ranked by
BM25 with the title weighted far above the body. This costs nothing, needs no
model, and runs against the index rather than loading every description into
memory — which is why it is the default and why the app works on a laptop with a
Copilot seat and nothing else.

**Vector (when it is free).** If the selected provider happens to expose an
embeddings endpoint — a local Ollama server, or an OpenAI-style endpoint that is
already configured — cosine similarity is a better recall signal and is used
instead. Copilot has no embeddings API, so this simply never switches on for the
default setup. It is an upgrade, never a requirement.
"""

from __future__ import annotations

import math
import re
from typing import Any

from joblookup.config import Settings
from joblookup.db import session as db
from joblookup.events import EventBus
from joblookup.llm import LLMClient
from joblookup.llm.base import LLMError

# Words that appear in every posting carry no signal and cost query time.
# Written as prose because a 130-element list literal is unreadable and unmaintainable.
_STOPWORD_SOURCE = """
    a about above after again against all am an and any are as at be because been before being
    below between both but by can cannot could did do does doing down during each few for from
    further had has have having he her here hers him his how i if in into is it its itself me
    more most my no nor not of off on once only or other our out over own same she should so
    some such than that the their them then there these they this those through to too under
    until up very was we were what when where which while who whom why will with you your
    role job work team company experience years year skills strong ability please apply
    candidate opportunity position
"""
STOPWORDS = frozenset(_STOPWORD_SOURCE.split())

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}")


def query_terms(text: str, limit: int = 60) -> list[str]:
    """The most distinctive terms in the profile, most frequent first.

    Frequency is the right ordering here because :func:`profile_text` already
    repeats what matters — core skills appear twice, target titles once per
    mention — so counting is a proxy for the weighting the profile expresses.
    """
    counts: dict[str, int] = {}
    for match in _TOKEN_RE.finditer(text or ""):
        token = match.group(0).strip(".-").lower()
        if len(token) < 2 or token in STOPWORDS or token.isdigit():
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ranked[:limit]]


def _fts_query(terms: list[str]) -> str:
    """FTS5 MATCH expression. Terms are quoted, so punctuation cannot become syntax."""
    escaped = [f'"{term.replace(chr(34), "")}"' for term in terms if term]
    return " OR ".join(escaped)


def lexical_recall(profile_text: str, settings: Settings, *, limit: int) -> list[tuple[int, float]]:
    terms = query_terms(profile_text)
    if not terms:
        return []

    # Title, company, location, description — in the column order of job_fts.
    # A title match is worth far more than a body match: descriptions mention
    # every adjacent technology, titles state what the job is.
    sql = """
        SELECT job.id AS id, bm25(job_fts, 12.0, 2.0, 1.5, 1.0) AS rank
        FROM job_fts
        JOIN job ON job.id = job_fts.rowid
        WHERE job_fts MATCH ? AND job.archived = 0 AND job.hidden = 0
        ORDER BY rank
        LIMIT ?
    """
    try:
        rows = db.connect().execute(sql, (_fts_query(terms), limit)).fetchall()
    except Exception:  # noqa: BLE001 - a malformed MATCH must not take the run down
        return _fallback_recall(terms, limit)

    if not rows:
        return []
    # bm25() returns a negative number where more negative is better.
    scores = [(int(row["id"]), -float(row["rank"])) for row in rows]
    return _normalise(scores)


def _fallback_recall(terms: list[str], limit: int) -> list[tuple[int, float]]:
    """Plain LIKE scoring, for the rare build without a usable FTS5."""
    if not terms:
        return []
    top = terms[:12]
    scoring = " + ".join(
        "(CASE WHEN title LIKE ? THEN 3 ELSE 0 END) + "
        "(CASE WHEN description LIKE ? THEN 1 ELSE 0 END)"
        for _ in top
    )
    params: list[Any] = []
    for term in top:
        params += [f"%{term}%", f"%{term}%"]
    rows = (
        db.connect()
        .execute(
            f"SELECT id, ({scoring}) AS score FROM job "
            "WHERE archived = 0 AND hidden = 0 ORDER BY score DESC LIMIT ?",
            [*params, limit],
        )
        .fetchall()
    )
    scores = [(int(row["id"]), float(row["score"])) for row in rows if row["score"] > 0]
    return _normalise(scores)


def _normalise(scores: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Map raw scores onto 0..1 so the threshold in settings means something.

    Scaled against the best hit rather than min-max: min-max always assigns
    exactly 0.0 to the weakest result, which then falls below any threshold at
    all. With a handful of candidates that silently discards half of them.
    """
    if not scores:
        return []
    best = max(value for _, value in scores)
    if best <= 0:
        return [(job_id, 1.0) for job_id, _ in scores]
    return [(job_id, min(1.0, max(0.0, value / best))) for job_id, value in scores]


# --- vector path -------------------------------------------------------------
def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def embeddings_available(client: LLMClient, settings: Settings) -> bool:
    if not settings.embeddings.enabled or not client.supports_embeddings:
        return False
    configured = settings.embeddings.model or getattr(settings.llm.openai_compat, "embed_model", "")
    return bool(configured)


def vector_recall(
    profile_text: str,
    client: LLMClient,
    settings: Settings,
    bus: EventBus,
    *,
    limit: int,
) -> list[tuple[int, float]] | None:
    """Cosine similarity over embeddings, or ``None`` if that is not possible.

    Returning ``None`` rather than raising is deliberate: a provider without
    embeddings is the normal case, not an error the user has to fix.
    """
    if not embeddings_available(client, settings):
        return None

    model = settings.embeddings.model or settings.llm.openai_compat.embed_model
    try:
        profile_vector = client.embed([profile_text], model=model)[0]
    except LLMError as exc:
        bus.warn(f"Embeddings unavailable ({exc}). Using keyword recall instead.", stage="recall")
        return None

    rows = (
        db.connect()
        .execute(
            "SELECT id, title, company, location, substr(description, 1, 2000) AS description, "
            "embedding, embed_model FROM job WHERE archived = 0 AND hidden = 0"
        )
        .fetchall()
    )
    if not rows:
        return []

    pending: list[tuple[int, str]] = []
    vectors: dict[int, list[float]] = {}
    for row in rows:
        stored = db.unpack_vector(row["embedding"])
        if stored and row["embed_model"] == model:
            vectors[int(row["id"])] = stored
        else:
            text = "\n".join(
                part
                for part in (row["title"], row["company"], row["location"], row["description"])
                if part
            )
            pending.append((int(row["id"]), text))

    if pending:
        bus.log(f"Embedding {len(pending)} new posting(s).", stage="recall")
        batch_size = max(1, settings.embeddings.batch_size)
        computed: list[tuple[int, list[float]]] = []
        for start in range(0, len(pending), batch_size):
            chunk = pending[start : start + batch_size]
            try:
                produced = client.embed([text for _, text in chunk], model=model)
            except LLMError as exc:
                bus.warn(
                    f"Embedding failed part-way ({exc}). Using keyword recall.", stage="recall"
                )
                return None
            for (job_id, _), vector in zip(chunk, produced, strict=True):
                vectors[job_id] = vector
                computed.append((job_id, vector))
            bus.progress("recall", (start + len(chunk)) / len(pending), "Embedding postings")
        from joblookup import store

        store.save_job_embeddings(computed, model)

    scored = [(job_id, cosine(profile_vector, vector)) for job_id, vector in vectors.items()]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


# --- entry point -------------------------------------------------------------
def recall(
    profile_text: str,
    client: LLMClient,
    settings: Settings,
    bus: EventBus,
) -> tuple[list[tuple[int, float]], str]:
    """Return ``(ranked_job_ids_with_scores, mode_used)``."""
    limit = max(1, settings.matching.recall_top_k)
    mode = settings.matching.recall_mode

    if mode in {"auto", "vector"}:
        vectors = vector_recall(profile_text, client, settings, bus, limit=limit)
        if vectors is not None:
            return _threshold(vectors, settings), "vector"
        if mode == "vector":
            bus.warn(
                "Vector recall was requested but the selected provider cannot produce "
                "embeddings. Falling back to keyword recall.",
                stage="recall",
            )

    return _threshold(lexical_recall(profile_text, settings, limit=limit), settings), "lexical"


def _threshold(scores: list[tuple[int, float]], settings: Settings) -> list[tuple[int, float]]:
    floor = settings.matching.recall_min_score
    return [(job_id, score) for job_id, score in scores if score >= floor]
