"""Keeping the career profile in step with the CVs and the wizard answers."""

from __future__ import annotations

from typing import Any

from joblookup import store
from joblookup.config import Settings
from joblookup.cv import extract as cv_extract
from joblookup.cv import profile as profile_merge
from joblookup.events import EventBus, NullBus
from joblookup.llm import LLMClient

#: Keys the user owns. Rebuilding must never clobber them.
PREFERENCE_KEYS = profile_merge.PREFERENCE_KEYS

#: Keys the user may have hand-corrected after a bad extraction.
MANUAL_KEYS = ("headline", "summary", "seniority", "full_name", "email", "phone")


def preferences() -> dict[str, Any]:
    data = store.get_profile().get("data") or {}
    kept = {key: data[key] for key in PREFERENCE_KEYS if key in data}
    kept.update({key: data[key] for key in data.get("_manual", []) if key in data})
    kept["_manual"] = data.get("_manual", [])
    return kept


def rebuild(settings: Settings, *, bump: bool = True) -> dict[str, Any]:
    """Re-merge every extracted CV into one profile, keeping the user's answers."""
    extractions = [
        cv.get("extracted") or {}
        for cv in store.list_cvs()
        if cv.get("extract_state") == "ok" and cv.get("extracted")
    ]
    kept = preferences()
    manual = list(kept.pop("_manual", []))

    merged = profile_merge.merge(extractions, kept, settings)
    # A field the user corrected by hand outranks anything re-read from a file.
    for key in manual:
        if key in kept:
            merged[key] = kept[key]
    merged["_manual"] = manual

    store.save_profile(merged, bump=bump)
    return merged


def apply_patch(settings: Settings, patch: dict[str, Any]) -> dict[str, Any]:
    """Save wizard answers and hand edits, then re-merge."""
    data = store.get_profile().get("data") or {}
    manual = set(data.get("_manual") or [])

    for key, value in patch.items():
        if value is None:
            continue
        data[key] = value
        if key in MANUAL_KEYS:
            manual.add(key)
    data["_manual"] = sorted(manual)

    store.save_profile(data, bump=False)
    return rebuild(settings)


def extract_cv(
    cv_id: int,
    client: LLMClient,
    settings: Settings,
    bus: EventBus | None = None,
) -> dict[str, Any]:
    """Read one CV with the model and fold the result into the profile."""
    bus = bus or NullBus()
    record = store.get_cv(cv_id)
    if not record:
        raise ValueError(f"CV {cv_id} no longer exists.")

    label = record.get("label") or record.get("filename") or f"CV {cv_id}"
    bus.stage_start("extract", f"Reading {label}")
    store.set_cv_extraction(cv_id, state="running", extracted=None)

    try:
        extracted = cv_extract.extract(client, record.get("raw_text") or "", settings)
    except Exception as exc:  # noqa: BLE001
        store.set_cv_extraction(cv_id, state="failed", extracted=None, error=str(exc))
        raise

    store.set_cv_extraction(cv_id, state="ok", extracted=extracted)
    skills = len(extracted.get("skills") or [])
    roles = len(extracted.get("roles") or [])
    bus.stage_end("extract", f"{skills} skill(s), {roles} role(s)")

    bus.stage_start("merge", "Updating your profile")
    merged = rebuild(settings)
    bus.stage_end(
        "merge",
        f"{len(merged.get('skills') or [])} skill(s) across "
        f"{merged.get('source_cv_count', 0)} CV(s)",
    )
    return {"cv_id": cv_id, "extracted": extracted, "profile": merged}


def onboarding_state(settings: Settings) -> dict[str, Any]:
    """What the user still has to do before a search is worth running."""
    counts = store.counts()
    profile = store.get_profile().get("data") or {}
    return {
        "has_cv": counts["cvs"] > 0,
        "has_profile": bool(profile.get("skills") or profile.get("target_titles")),
        "has_targets": bool(profile.get("target_titles")),
        "has_sources": counts["sources_enabled"] > 0,
        "has_jobs": counts["jobs"] > 0,
        "has_scores": counts["scored"] > 0,
    }
