"""Layered configuration: ``config/default.yaml`` → ``config/local.yaml`` →
environment variables → an explicit override file.

The result is a validated :class:`Settings` object. Nothing else in the codebase
reads YAML or environment variables directly.

Two rules shape this file:

* **Every number that affects behaviour is here.** If the app makes a judgement
  call — how many jobs to score, how wide to cast the net, how long to wait — the
  user can change it without editing code.
* **Defaults have to be good enough that nobody must.**
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from joblookup.paths import app_root, resolve

DEFAULT_CONFIG = "config/default.yaml"
LOCAL_CONFIG = "config/local.yaml"
ENV_PREFIX = "JOBLOOKUP_"

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]


# --- server and storage ------------------------------------------------------
class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8770
    allowed_origins: list[str] = Field(default_factory=list)
    max_upload_mb: int = 64
    #: Hosted mode. Requires an authenticating reverse proxy in front; see README.
    multi_user: bool = False
    identity_header: str = "x-joblookup-user"
    proxy_secret_header: str = "x-joblookup-proxy-secret"
    proxy_secret_env: str = "JOBLOOKUP_PROXY_SECRET"


class PathsConfig(BaseModel):
    workspace: str = "workspace"
    vendor: str = "vendor"

    @property
    def workspace_dir(self) -> Path:
        return resolve(self.workspace)

    @property
    def vendor_dir(self) -> Path:
        return resolve(self.vendor)


# --- language model ----------------------------------------------------------
class VSCodeLLMConfig(BaseModel):
    handshake_file: str | None = None
    base_url: str | None = None
    token: str | None = None
    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    context_window_tokens: int | None = Field(default=None, ge=1024, le=2_000_000)
    request_timeout_s: float = 180.0


class CopilotCliConfig(BaseModel):
    command: str = "copilot"
    extra_args: list[str] = Field(default_factory=lambda: ["--no-color"])
    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    context_window: Literal["default", "long_context"] = "default"
    request_timeout_s: float = 300.0


class OpenAICompatConfig(BaseModel):
    #: Which entry in llm/presets.py filled these in, for the UI to show.
    preset: str = "ollama"
    base_url: str | None = None
    api_key_env: str = "JOBLOOKUP_LLM_API_KEY"
    model: str = "llama3.1:8b"
    auth_style: str = "bearer"
    request_timeout_s: float = 180.0
    #: Endpoint used for embeddings when this provider supports them.
    embed_model: str = ""


class AnthropicConfig(BaseModel):
    base_url: str = "https://api.anthropic.com"
    api_key_env: str = "JOBLOOKUP_ANTHROPIC_API_KEY"
    model: str = "claude-sonnet-4-5"
    max_tokens: int = 8192
    request_timeout_s: float = 180.0


class LLMConfig(BaseModel):
    provider: str = "vscode"
    vscode: VSCodeLLMConfig = Field(default_factory=VSCodeLLMConfig)
    copilot_cli: CopilotCliConfig = Field(default_factory=CopilotCliConfig)
    openai_compat: OpenAICompatConfig = Field(default_factory=OpenAICompatConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    #: How many times to re-ask when a reply will not parse as JSON.
    json_retries: int = 2
    #: Requests in flight at once. Copilot rate-limits, so keep this modest.
    max_concurrency: int = 2


# --- searching ---------------------------------------------------------------
class SearchConfig(BaseModel):
    """How wide and how hard to crawl the job sources."""

    #: A month-old posting is usually filled. Seven days is the useful window.
    recency_days: int = 7
    max_jobs_per_source: int = 200
    #: Which country pack the Sources screen is showing. "remote" ignores
    #: geography and filters results down to remote roles. See sources/regions.py
    #: for the codes; it is not imported here to keep config free of dependencies.
    region: str = "in"
    #: Drop anything not positively identified as remote. Independent of the pack,
    #: so "India, but only remote roles" is a combination the user can ask for.
    remote_only: bool = False
    #: Politeness floor applied to every HTTP source, on top of any per-source rate.
    min_request_interval_s: float = 1.0
    http_timeout_s: float = 30.0
    max_concurrent_sources: int = 4
    user_agent: str = "JobLookup/0.1 (personal job search tool)"
    #: Drop postings whose description is shorter than this; they carry no signal.
    min_description_chars: int = 120
    #: Stop tracking a job that has not been seen for this long.
    archive_after_days: int = 45


class TierBConfig(BaseModel):
    """Logged-in portal scraping. Off until the user opts in, per portal."""

    enabled: bool = False
    headless: bool = False
    #: Human-paced throttling. Lowering these is what gets accounts banned.
    min_action_delay_s: float = 2.5
    max_action_delay_s: float = 7.0
    max_pages_per_run: int = 5
    daily_run_cap: int = 3
    nav_timeout_s: float = 45.0


class DedupeConfig(BaseModel):
    """When two postings are the same job rather than sibling roles."""

    #: Title similarity above this, at the same company, collapses into one card.
    title_similarity: float = 0.88
    #: Locations this far apart keep the postings separate.
    require_same_location: bool = True
    #: Treat descriptions as the same job when they overlap this much.
    description_similarity: float = 0.92


class MatchingConfig(BaseModel):
    """Recall, prefilter, scoring and banding.

    The pipeline is deliberately three-staged so the model is only ever asked
    about jobs that are plausibly relevant: cheap recall over everything, a
    free heuristic prefilter, then batched LLM judgement on what survives.
    """

    # -- stage 1: recall
    #: "auto" uses embeddings when the active provider can produce them and
    #: falls back to lexical scoring otherwise. "lexical" and "vector" force it.
    recall_mode: Literal["auto", "lexical", "vector"] = "auto"
    recall_top_k: int = 300
    recall_min_score: float = 0.12

    # -- stage 2: prefilter (no model calls, no cost)
    prefilter_enabled: bool = True
    #: How many of the recalled jobs reach the model. Raise for coverage,
    #: lower to spend less of your Copilot quota.
    prefilter_keep: int = 120
    #: Postings whose seniority is this many levels above the profile are dropped.
    max_seniority_jump: int = 1

    # -- stage 3: LLM scoring
    #: Jobs judged per model call. One call per job is accurate but slow and
    #: expensive; 12 keeps the prompt comfortable on a 8k-token window.
    score_batch_size: int = 12
    #: Characters of each job description sent to the model.
    description_chars: int = 1800
    #: Re-score jobs already scored against the current profile version.
    rescore_existing: bool = False

    # -- banding
    strong_threshold: float = 0.75
    good_threshold: float = 0.55
    stretch_threshold: float = 0.35
    #: Transferable fit is weighted heavily on purpose. Most people are hired
    #: into roles they have not held before; filtering on exact matches only
    #: shows you the jobs you already have.
    weight_direct: float = 0.45
    weight_transferable: float = 0.40
    weight_growth: float = 0.15

    dedupe: DedupeConfig = Field(default_factory=DedupeConfig)


class EmbeddingsConfig(BaseModel):
    """Vector recall, used only when it is free to do so.

    Copilot exposes no embeddings API, so this stays off unless the selected
    provider happens to offer one (a local Ollama server, or an OpenAI-style
    endpoint that is already configured). Nothing here ever becomes a
    requirement.
    """

    enabled: bool = True
    #: Named model on whichever provider is answering. Blank uses the preset default.
    model: str = ""
    dimensions: int = 0
    batch_size: int = 32
    #: Give up on vectors after this long and use lexical recall instead.
    timeout_s: float = 20.0


class ProfileConfig(BaseModel):
    """How several CVs become one career profile."""

    #: A skill named in this fraction of your CVs is treated as core.
    core_skill_threshold: float = 0.5
    max_skills: int = 80
    #: Characters of CV text handed to the model in one extraction pass.
    extract_window_chars: int = 12000


class TailorConfig(BaseModel):
    """Rewriting a CV for one specific posting."""

    #: 0 = only what the CV already says. Higher lets the model reframe more
    #: freely. It may never invent experience at any setting.
    enrichment: int = 0
    #: Skills you do not have appear only under this heading, never inline.
    upskilling_heading: str = "Currently upskilling"
    include_upskilling_section: bool = True
    #: Strip the vocabulary and typography that make writing read as generated.
    style_guard: bool = True
    max_bullets_per_role: int = 6
    template: str = ""
    output_format: Literal["docx", "markdown", "both"] = "both"


class SchedulerConfig(BaseModel):
    enabled: bool = False
    hour: int = 8
    minute: int = 0
    #: Empty means every day. Otherwise 0=Monday … 6=Sunday.
    weekdays: list[int] = Field(default_factory=list)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str | None = None


class Settings(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    tier_b: TierBConfig = Field(default_factory=TierBConfig)
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    profile: ProfileConfig = Field(default_factory=ProfileConfig)
    tailor: TailorConfig = Field(default_factory=TailorConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


# --- loading -----------------------------------------------------------------
def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _coerce(raw: str) -> Any:
    """Turn an environment string into the type the field probably wants."""
    lowered = raw.strip().lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "none", ""}:
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if raw.startswith(("[", "{")):
        try:
            return yaml.safe_load(raw)
        except yaml.YAMLError:
            return raw
    return raw


def _env_overlay(model: type[BaseModel], prefix: str) -> dict[str, Any]:
    """Walk the model tree and pick up ``JOBLOOKUP_SECTION_KEY`` variables.

    Driven by the model rather than by parsing variable names, so an env var can
    only ever reach a field that actually exists.
    """
    overlay: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            nested = _env_overlay(annotation, f"{prefix}{name.upper()}_")
            if nested:
                overlay[name] = nested
            continue
        raw = os.environ.get(f"{prefix}{name.upper()}")
        if raw is not None:
            overlay[name] = _coerce(raw)
    return overlay


def load_settings(override: str | Path | None = None) -> Settings:
    root = app_root()
    data = _read_yaml(root / DEFAULT_CONFIG)
    data = _deep_merge(data, _read_yaml(root / LOCAL_CONFIG))
    if override:
        data = _deep_merge(data, _read_yaml(Path(override).expanduser().resolve()))
    data = _deep_merge(data, _env_overlay(Settings, ENV_PREFIX))
    return Settings.model_validate(data)


def local_config_path() -> Path:
    return app_root() / LOCAL_CONFIG


def read_local_overrides() -> dict[str, Any]:
    return _read_yaml(local_config_path())


def save_local_overrides(patch: dict[str, Any]) -> Settings:
    """Merge ``patch`` into ``config/local.yaml`` and return the new settings.

    Only the difference from the defaults is written, so a later change to
    ``default.yaml`` still reaches anyone who never overrode that value.
    """
    path = local_config_path()
    merged = _deep_merge(_read_yaml(path), patch)
    # Validate before writing: a bad value should be rejected, not persisted.
    candidate = _deep_merge(_read_yaml(app_root() / DEFAULT_CONFIG), merged)
    Settings.model_validate(candidate)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(merged, handle, sort_keys=False, allow_unicode=True)
    return load_settings()
