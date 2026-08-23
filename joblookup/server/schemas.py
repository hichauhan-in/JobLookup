"""Request bodies.

Responses are plain dictionaries built by the store, because the browser is the
only consumer and a second definition of every field would go stale.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SettingsPatch(BaseModel):
    """A partial settings tree, merged into ``config/local.yaml``."""

    patch: dict[str, Any] = Field(default_factory=dict)


class ProviderChoice(BaseModel):
    provider: str
    #: For openai_compat / anthropic: which entry in llm/presets.py to apply.
    preset: str = ""
    base_url: str | None = None
    model: str | None = None
    embed_model: str | None = None
    reasoning_effort: str | None = None
    context_window_tokens: int | None = None


class SecretPatch(BaseModel):
    name: str
    value: str = ""


class SourceToggle(BaseModel):
    enabled: bool


class RiskAck(BaseModel):
    acknowledged: bool


class SourceConfigPatch(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class RegionSelect(BaseModel):
    code: str
    #: Switch on everything in the pack that can already run, rather than only
    #: showing it. Selecting a pack alone changes nothing but the view.
    apply: bool = False
    #: How many companies to spread across the pack's boards when applying.
    companies: int = Field(default=60, ge=0, le=400)
    #: Replace the pack's previous choices rather than adding to them.
    replace: bool = True


class BudgetPreview(BaseModel):
    #: None means "whatever is currently saved".
    economy: int | None = Field(default=None, ge=0, le=100)
    #: How many postings to price. Defaults to the saved shortlist size.
    postings: int | None = Field(default=None, ge=1, le=2000)
    #: Supplied by the browser so the preview does not re-probe the provider.
    models: list[str] = Field(default_factory=list)


class CompanySuggestRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=400)
    #: Empty means every board in the catalogue.
    boards: list[str] = Field(default_factory=list)
    #: Write the picks into each board's config, rather than only previewing.
    apply: bool = False
    #: Replace what is already there instead of adding to it.
    replace: bool = False


class ProfilePatch(BaseModel):
    """The wizard answers. Never overwritten by anything read from a CV."""

    target_titles: list[str] | None = None
    locations: list[str] | None = None
    work_modes: list[str] | None = None
    employment_types: list[str] | None = None
    recency_days: int | None = None
    work_authorization: str | None = None
    exclusions: list[str] | None = None
    min_salary: float | None = None
    salary_currency: str | None = None
    notes: str | None = None
    #: Direct edits to the merged profile, for fixing a bad extraction.
    headline: str | None = None
    summary: str | None = None
    seniority: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None


class SearchRequest(BaseModel):
    #: Empty means every enabled source.
    sources: list[str] = Field(default_factory=list)
    #: Run matching straight after the search finishes.
    then_match: bool = True
    # One-off tweaks from the dashboard. None means "use the saved setting", so
    # a quick adjustment never quietly becomes permanent.
    recency_days: int | None = Field(default=None, ge=1, le=365)
    prefilter_keep: int | None = Field(default=None, ge=1, le=2000)
    max_jobs_per_source: int | None = Field(default=None, ge=1, le=2000)
    remote_only: bool | None = None
    #: Write these tweaks back to config/local.yaml as the new defaults.
    remember: bool = False


class MatchRequest(BaseModel):
    rescore: bool = False


class ResetRequest(BaseModel):
    #: Also delete the stored postings, not only what they scored.
    postings: bool = False
    #: Keep any posting you are tracking, so an application is never lost.
    keep_tracked: bool = True


class JobFilter(BaseModel):
    bands: list[str] = Field(default_factory=list)
    work_modes: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    max_age_days: int | None = None
    query: str = ""
    include_hidden: bool = False
    scored_only: bool = True
    #: Limit to what one search produced. "latest" resolves on the server, so the
    #: browser does not have to know which run that is.
    run_id: int | None = None
    run: str = "latest"
    limit: int = 100
    offset: int = 0


class ApplicationPatch(BaseModel):
    status: str
    notes: str | None = None


class TailorRequest(BaseModel):
    cv_id: int | None = None
