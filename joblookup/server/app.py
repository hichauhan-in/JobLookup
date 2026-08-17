"""The HTTP + WebSocket API, and the static UI.

Everything the browser can do is here. The rules this file follows:

* Long work never blocks the event loop — it becomes a background task and
  streams progress over a WebSocket.
* Every path that comes from the client is resolved inside the workspace, and
  anything that escapes it is refused.
* Errors come back as a sentence a person can act on, not a stack trace.
"""

from __future__ import annotations

import asyncio
import hmac
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect

from joblookup import __version__, doctor, store
from joblookup.config import (
    Settings,
    load_settings,
    read_local_overrides,
    save_local_overrides,
)
from joblookup.cv import SUPPORTED_SUFFIXES, UnreadableCV, extract_text
from joblookup.db import session as db
from joblookup.events import EventBus
from joblookup.llm import LLMClient, all_statuses
from joblookup.llm import presets as llm_presets
from joblookup.llm.vscode_bridge import extension_state
from joblookup.matching.pipeline import ProfileMissing, run_matching
from joblookup.models import APPLICATION_STATUSES
from joblookup.paths import ensure_dir, isolated_user_dir, web_dir
from joblookup.server import schemas
from joblookup.server.jobs import Job, manager
from joblookup.services import crawl, profiling, secrets, suggest
from joblookup.services.scheduler import Scheduler
from joblookup.sources import catalogue, regions, registry
from joblookup.sources.base import as_list
from joblookup.sources.tier_b import browser as tier_b_browser
from joblookup.sources.tier_b.portal import RISK_NOTICE, PortalAdapter
from joblookup.tailor import build as build_docx
from joblookup.tailor import prep_markdown, tailor

_settings_lock = threading.Lock()
_settings: Settings | None = None


# --- settings access ---------------------------------------------------------
def current_settings() -> Settings:
    global _settings
    with _settings_lock:
        if _settings is None:
            _settings = load_settings()
        return _settings


def reload_settings() -> Settings:
    global _settings
    with _settings_lock:
        _settings = load_settings()
        return _settings


def client_for(settings: Settings) -> LLMClient:
    return LLMClient.from_settings(settings)


def _scheduled_search() -> None:
    """What the scheduler fires. Goes through the same queue as a manual run, so
    a scheduled search cannot collide with one the user started."""
    settings = current_settings()

    def work(bus: EventBus, job: Job) -> dict[str, Any]:
        stats = crawl.run_crawl(settings, bus, cancelled=job.cancel_requested.is_set)
        result: dict[str, Any] = {"crawl": stats.to_dict()}
        try:
            result["match"] = run_matching(
                settings, client_for(settings), bus, cancelled=job.cancel_requested.is_set
            )
        except ProfileMissing as exc:
            bus.warn(str(exc), stage="score")
        return result

    manager.submit("search", work, label="Scheduled search")


_scheduler = Scheduler(current_settings, _scheduled_search)


# --- hosted mode -------------------------------------------------------------
def _identity(request: Request, settings: Settings) -> str:
    """Who is asking, in hosted mode.

    Single-user mode has exactly one identity. Hosted mode requires both a proxy
    secret the browser cannot know and a subject the proxy injected, so a client
    cannot promote itself by setting a header.
    """
    if not settings.server.multi_user:
        return ""

    expected = os.environ.get(settings.server.proxy_secret_env, "")
    provided = request.headers.get(settings.server.proxy_secret_header, "")
    if not expected or not hmac.compare_digest(expected, provided):
        raise HTTPException(401, "This deployment requires an authenticating proxy.")

    subject = request.headers.get(settings.server.identity_header, "").strip()
    if not subject:
        raise HTTPException(401, "The proxy did not supply an identity.")
    return subject


def storage_root(request: Request | None = None) -> Path:
    settings = current_settings()
    root = settings.paths.workspace_dir
    if settings.server.multi_user and request is not None:
        return isolated_user_dir(root, _identity(request, settings))
    return ensure_dir(root)


def uploads_dir() -> Path:
    return ensure_dir(current_settings().paths.workspace_dir / "uploads")


def exports_dir() -> Path:
    return ensure_dir(current_settings().paths.workspace_dir / "exports")


def _inside(root: Path, candidate: Path) -> Path:
    """Refuse any path that leaves ``root``, however it was constructed."""
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise HTTPException(400, "That path is outside the workspace.")
    return resolved


# --- application -------------------------------------------------------------
def create_app(settings: Settings | None = None) -> FastAPI:
    global _settings
    _settings = settings or load_settings()
    active = _settings

    db.configure(active.paths.workspace_dir)
    registry.sync_source_table()
    manager.start()
    _scheduler.start()

    app = FastAPI(title="JobLookup", version=__version__, docs_url="/api/docs")

    if active.server.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=active.server.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    _register_routes(app)

    web = web_dir()
    if web.is_dir():
        app.mount("/", RevalidatingStatics(directory=str(web), html=True), name="web")
    return app


class RevalidatingStatics(StaticFiles):
    """Static files that must be re-checked on every request.

    Without this the browser applies heuristic caching and an updated build
    silently serves the previous stylesheet. A 304 on localhost costs nothing;
    a stale UI after an update costs a support conversation.
    """

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["cache-control"] = "no-cache"
        return response


def _register_routes(app: FastAPI) -> None:  # noqa: C901 - one router, read top to bottom
    # --- state ------------------------------------------------------------
    @app.get("/api/state")
    def get_state(request: Request) -> dict[str, Any]:
        settings = current_settings()
        _identity(request, settings)
        provider = None
        try:
            provider = client_for(settings).status().to_dict()
        except Exception as exc:  # noqa: BLE001
            provider = {"key": settings.llm.provider, "available": False, "detail": str(exc)}
        return {
            "version": __version__,
            "provider": provider,
            "bridge": extension_state(settings.llm.vscode.handshake_file),
            "counts": store.counts(),
            "onboarding": profiling.onboarding_state(settings),
            "tasks": manager.active(),
            "multi_user": settings.server.multi_user,
        }

    @app.get("/api/health")
    def get_health() -> dict[str, Any]:
        return doctor.run_all(current_settings())

    @app.get("/api/paths")
    def get_paths() -> dict[str, str]:
        return doctor.paths_report(current_settings())

    # --- settings ---------------------------------------------------------
    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        """Everything the Settings screen can show immediately.

        Provider statuses are deliberately not here: probing every provider
        means several network round trips, which used to hold this whole screen
        blank for seconds. They come from /api/llm/providers instead, and the
        model card fills itself in when that lands.
        """
        settings = current_settings()
        return {
            "settings": settings.model_dump(mode="json"),
            "overrides": read_local_overrides(),
            "presets": llm_presets.as_dicts(),
            "secrets": secrets.status(),
        }

    @app.get("/api/llm/providers")
    def get_providers() -> dict[str, Any]:
        """Probe every provider. Slow by nature, so it is asked for on its own."""
        return {"providers": [status.to_dict() for status in all_statuses(current_settings().llm)]}

    @app.post("/api/settings")
    def post_settings(body: schemas.SettingsPatch) -> dict[str, Any]:
        try:
            save_local_overrides(body.patch)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"Those settings were rejected: {exc}") from exc
        settings = reload_settings()
        return {"settings": settings.model_dump(mode="json"), "overrides": read_local_overrides()}

    @app.post("/api/llm/provider")
    def post_provider(body: schemas.ProviderChoice) -> dict[str, Any]:
        """Switch provider, filling in a preset's endpoint and auth style."""
        patch: dict[str, Any] = {"llm": {"provider": body.provider}}

        if body.preset:
            preset = llm_presets.get(body.preset)
            if preset is None:
                raise HTTPException(400, f"There is no preset called '{body.preset}'.")
            patch["llm"]["provider"] = preset.provider
            if preset.provider == "anthropic":
                patch["llm"]["anthropic"] = {
                    "base_url": preset.base_url,
                    "api_key_env": preset.api_key_env,
                    "model": body.model or preset.suggested_models[0],
                }
            else:
                patch["llm"]["openai_compat"] = {
                    "preset": preset.key,
                    "base_url": body.base_url or preset.base_url,
                    "api_key_env": preset.api_key_env,
                    "auth_style": preset.auth_style,
                    "model": body.model
                    or (preset.suggested_models[0] if preset.suggested_models else ""),
                    "embed_model": body.embed_model
                    or (preset.suggested_embed_models[0] if preset.suggested_embed_models else ""),
                }
        elif body.provider == "vscode":
            vscode: dict[str, Any] = {}
            if body.model is not None:
                vscode["model"] = body.model or None
            if body.reasoning_effort:
                vscode["reasoning_effort"] = body.reasoning_effort
            if body.context_window_tokens:
                vscode["context_window_tokens"] = body.context_window_tokens
            if vscode:
                patch["llm"]["vscode"] = vscode
        elif body.provider == "copilot_cli" and body.model is not None:
            patch["llm"]["copilot_cli"] = {"model": body.model or None}

        try:
            save_local_overrides(patch)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc)) from exc
        settings = reload_settings()
        return {"provider": client_for(settings).status().to_dict()}

    @app.post("/api/llm/test")
    def post_llm_test() -> dict[str, Any]:
        settings = current_settings()
        client = client_for(settings)
        status = client.status()
        if not status.available:
            return {"ok": False, "detail": status.detail, "fix": status.setup_hint}
        try:
            reply = client.complete(
                "You are a connection test. Answer in one word.",
                "Reply with the single word: ready",
                temperature=0.0,
                max_tokens=16,
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": str(exc), "fix": status.setup_hint}
        return {"ok": True, "detail": reply.strip()[:120], "model": status.active_model}

    @app.get("/api/secrets")
    def get_secrets() -> dict[str, Any]:
        return secrets.status()

    @app.post("/api/secrets")
    def post_secret(body: schemas.SecretPatch) -> dict[str, Any]:
        if body.name not in secrets.KNOWN:
            raise HTTPException(400, f"'{body.name}' is not a key JobLookup uses.")
        secrets.set(body.name, body.value)
        return secrets.status()

    # --- CVs --------------------------------------------------------------
    @app.get("/api/cvs")
    def get_cvs() -> dict[str, Any]:
        return {"cvs": store.list_cvs()}

    @app.post("/api/cvs")
    async def post_cv(file: UploadFile = File(...), label: str = Form("")) -> dict[str, Any]:
        settings = current_settings()
        original = Path(file.filename or "cv")
        suffix = original.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES and suffix != ".doc":
            raise HTTPException(
                400,
                f"{suffix or 'That file type'} is not supported. Upload a PDF, DOCX, "
                "TXT or Markdown file.",
            )

        limit = settings.server.max_upload_mb * 1024 * 1024
        # A generated name means a hostile filename can never reach the filesystem.
        destination = uploads_dir() / f"{uuid.uuid4().hex[:12]}{suffix}"
        size = 0
        try:
            with destination.open("wb") as handle:
                while chunk := await file.read(1024 * 512):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(
                            413, f"That file is larger than {settings.server.max_upload_mb} MB."
                        )
                    handle.write(chunk)
        except HTTPException:
            destination.unlink(missing_ok=True)
            raise

        try:
            text = await asyncio.to_thread(extract_text, destination)
        except UnreadableCV as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(400, str(exc)) from exc

        cv_id = store.add_cv(
            label=label.strip() or original.stem,
            filename=original.name,
            stored_path=destination,
            mime_type=file.content_type or "",
            raw_text=text,
        )
        task = _submit_extract(cv_id)
        return {"cv_id": cv_id, "task": task.summary(), "chars": len(text)}

    @app.post("/api/cvs/{cv_id}/extract")
    def post_cv_extract(cv_id: int) -> dict[str, Any]:
        if not store.get_cv(cv_id):
            raise HTTPException(404, "That CV no longer exists.")
        return {"task": _submit_extract(cv_id).summary()}

    @app.post("/api/cvs/{cv_id}/primary")
    def post_cv_primary(cv_id: int) -> dict[str, Any]:
        if not store.get_cv(cv_id):
            raise HTTPException(404, "That CV no longer exists.")
        store.set_primary_cv(cv_id)
        return {"cvs": store.list_cvs()}

    @app.delete("/api/cvs/{cv_id}")
    def delete_cv(cv_id: int) -> dict[str, Any]:
        stored = store.delete_cv(cv_id)
        if stored:
            try:
                _inside(uploads_dir(), Path(stored)).unlink(missing_ok=True)
            except HTTPException:
                pass
        profiling.rebuild(current_settings())
        return {"cvs": store.list_cvs(), "profile": store.get_profile()}

    # --- profile ----------------------------------------------------------
    @app.get("/api/profile")
    def get_profile() -> dict[str, Any]:
        row = store.get_profile()
        row.pop("embedding", None)
        return {"profile": row, "onboarding": profiling.onboarding_state(current_settings())}

    @app.put("/api/profile")
    def put_profile(body: schemas.ProfilePatch) -> dict[str, Any]:
        patch = {key: value for key, value in body.model_dump().items() if value is not None}
        merged = profiling.apply_patch(current_settings(), patch)
        return {"profile": {"data": merged, "version": store.profile_version()}}

    @app.post("/api/profile/rebuild")
    def post_profile_rebuild() -> dict[str, Any]:
        merged = profiling.rebuild(current_settings())
        return {"profile": {"data": merged, "version": store.profile_version()}}

    @app.post("/api/quit")
    def post_quit(request: Request) -> dict[str, Any]:
        """Stop the app from the sidebar, so nobody has to hunt for the terminal."""
        settings = current_settings()
        if settings.server.multi_user:
            raise HTTPException(400, "Quitting from the browser is disabled in hosted mode.")
        # The one irreversible endpoint, so it refuses anything a browser marks
        # as coming from another site even if CORS were opened up later.
        if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
            raise HTTPException(403, "Quit can only be triggered from JobLookup itself.")
        stop = getattr(app.state, "request_shutdown", None)
        if stop is None:
            raise HTTPException(
                400,
                "This instance was not started by 'joblookup serve', so it cannot stop "
                "itself. Close it where you started it.",
            )
        # Give the response time to reach the browser before the socket dies.
        threading.Timer(0.4, stop).start()
        return {"stopping": True}

    # --- sources ----------------------------------------------------------
    @app.get("/api/sources")
    def get_sources() -> dict[str, Any]:
        settings = current_settings()
        return {
            "sources": registry.list_sources(settings),
            "tier_b_enabled": settings.tier_b.enabled,
            "risk_notice": RISK_NOTICE,
            "playwright": tier_b_browser.availability(),
            "region": registry.region_view(settings.search.region, settings),
            "remote_only": settings.search.remote_only,
            "regions": [
                {"code": region.code, "name": region.name} for region in regions.all_regions()
            ],
        }

    @app.post("/api/sources/region")
    def post_source_region(body: schemas.RegionSelect) -> dict[str, Any]:
        if regions.get(body.code) is None:
            raise HTTPException(404, f"There is no country pack called '{body.code}'.")
        save_local_overrides({"search": {"region": body.code}})
        settings = reload_settings()
        report = registry.apply_region(body.code, settings) if body.apply else None
        return {
            "sources": registry.list_sources(settings),
            "region": registry.region_view(body.code, settings),
            "applied": report,
        }

    # --- suggestions -------------------------------------------------------
    @app.post("/api/sources/suggest")
    def post_suggest_companies(body: schemas.CompanySuggestRequest) -> dict[str, Any]:
        """Rank the verified catalogue against the profile, and optionally apply it."""
        settings = current_settings()
        profile = store.get_profile().get("data") or {}
        picks = suggest.rank_companies(
            profile, settings, limit=body.limit, boards=body.boards or None
        )
        grouped = suggest.grouped_slugs(picks)

        applied: dict[str, int] = {}
        if body.apply:
            for board, slugs in grouped.items():
                if body.replace:
                    merged = slugs
                else:
                    existing = as_list(registry.source_config(board).get("slugs"))
                    merged = list(dict.fromkeys([*existing, *slugs]))
                registry.update_config(board, {"slugs": merged})
                if registry.get_adapter(board) is not None:
                    registry.set_enabled(board, True)
                applied[board] = len(merged)

        return {
            "suggestions": [pick.to_dict() for pick in picks],
            "grouped": grouped,
            "tags": sorted(suggest.profile_tags(profile)),
            "applied": applied,
            "verified_on": catalogue.VERIFIED_ON,
            "catalogue_size": len(catalogue.COMPANIES),
            "sources": registry.list_sources(settings) if body.apply else None,
        }

    @app.post("/api/profile/roles")
    def post_suggest_roles() -> dict[str, Any]:
        settings = current_settings()
        profile = store.get_profile().get("data") or {}
        try:
            client = client_for(settings)
        except Exception:  # noqa: BLE001
            client = None
        return suggest.suggest_roles(profile, client)

    @app.post("/api/sources/{key}/enabled")
    def post_source_enabled(key: str, body: schemas.SourceToggle) -> dict[str, Any]:
        adapter = registry.get_adapter(key)
        if adapter is None:
            raise HTTPException(404, f"There is no source called '{key}'.")
        settings = current_settings()
        if body.enabled and adapter.tier == "b":
            if not settings.tier_b.enabled:
                raise HTTPException(
                    400,
                    "Logged-in portal automation is switched off. Turn on tier_b.enabled "
                    "in Settings first, and read what it means before you do.",
                )
            if not registry.source_config(key).get("risk_ack"):
                raise HTTPException(400, "Accept the risk notice for this portal first.")
        registry.set_enabled(key, body.enabled)
        return {"sources": registry.list_sources(settings)}

    @app.post("/api/sources/{key}/risk")
    def post_source_risk(key: str, body: schemas.RiskAck) -> dict[str, Any]:
        if registry.get_adapter(key) is None:
            raise HTTPException(404, f"There is no source called '{key}'.")
        registry.set_risk_ack(key, body.acknowledged)
        if not body.acknowledged:
            registry.set_enabled(key, False)
        return {"sources": registry.list_sources(current_settings())}

    @app.post("/api/sources/{key}/config")
    def post_source_config(key: str, body: schemas.SourceConfigPatch) -> dict[str, Any]:
        if registry.get_adapter(key) is None:
            raise HTTPException(404, f"There is no source called '{key}'.")
        registry.update_config(key, body.config)
        return {"sources": registry.list_sources(current_settings())}

    @app.post("/api/sources/{key}/signin")
    def post_source_signin(key: str) -> dict[str, Any]:
        adapter = registry.get_adapter(key)
        if not isinstance(adapter, PortalAdapter):
            raise HTTPException(400, "That source does not use a browser sign-in.")
        settings = current_settings()
        if settings.server.multi_user:
            raise HTTPException(
                400,
                "Browser sign-in is disabled in hosted mode: it would open a window on "
                "the server, not on your machine.",
            )

        def work(bus: EventBus, job: Job) -> dict[str, Any]:
            bus.stage_start("signin", f"Opening {adapter.name}")
            bus.log("Sign in as you normally would, then close the browser window.")
            result = tier_b_browser.sign_in(settings, adapter.key, adapter.login_url)
            bus.stage_end(
                "signin", "Session saved" if result["session_saved"] else "No session was saved"
            )
            return result

        return {
            "task": manager.submit(
                "sign-in", work, label=f"Sign in to {adapter.name}", meta={"source": key}
            ).summary()
        }

    @app.post("/api/sources/{key}/test")
    def post_source_test(key: str) -> dict[str, Any]:
        adapter = registry.get_adapter(key)
        if not isinstance(adapter, PortalAdapter):
            raise HTTPException(400, "Selector testing only applies to logged-in portals.")
        settings = current_settings()
        titles, locations = crawl.profile_queries(settings)

        def work(bus: EventBus, job: Job) -> dict[str, Any]:
            bus.stage_start("test", f"Loading {adapter.name}")
            context = registry.context_for(
                key,
                settings,
                queries=titles,
                locations=locations,
                log=lambda message: bus.log(message, stage="test"),
            )
            report = adapter.test_selectors(context)
            matched = report.get("selectors", {}).get("card", {}).get("matched", 0)
            bus.stage_end("test", f"{matched} card(s) matched")
            return report

        return {
            "task": manager.submit(
                "test-selectors", work, label=f"Test {adapter.name}", meta={"source": key}
            ).summary()
        }

    @app.post("/api/sources/playwright/install")
    def post_playwright_install() -> dict[str, Any]:
        """Install Playwright and its Chromium, on request and never before."""
        import subprocess
        import sys

        def work(bus: EventBus, job: Job) -> dict[str, Any]:
            steps = (
                (
                    "Installing Playwright",
                    [sys.executable, "-m", "pip", "install", "playwright>=1.44"],
                ),
                (
                    "Downloading Chromium",
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                ),
            )
            for index, (label, command) in enumerate(steps, start=1):
                bus.stage_start("install", label)
                result = subprocess.run(command, capture_output=True, text=True)
                if result.returncode != 0:
                    raise RuntimeError(f"{label} failed: {(result.stderr or result.stdout)[-600:]}")
                bus.progress("install", index / len(steps), label)
            state = tier_b_browser.availability(refresh=True)
            bus.stage_end("install", state["detail"])
            return state

        return {"task": manager.submit("provision", work, label="Install Playwright").summary()}

    # --- searching and matching -------------------------------------------
    def _tuned(settings: Settings, body: schemas.SearchRequest) -> Settings:
        """Apply the dashboard's one-off tweaks without saving them."""
        overrides = {
            ("search", "recency_days"): body.recency_days,
            ("search", "max_jobs_per_source"): body.max_jobs_per_source,
            ("search", "remote_only"): body.remote_only,
            ("matching", "prefilter_keep"): body.prefilter_keep,
        }
        chosen = {path: value for path, value in overrides.items() if value is not None}
        if not chosen:
            return settings
        tuned = settings.model_copy(deep=True)
        for (section, key), value in chosen.items():
            setattr(getattr(tuned, section), key, value)
        if body.remember:
            patch: dict[str, Any] = {}
            for (section, key), value in chosen.items():
                patch.setdefault(section, {})[key] = value
            save_local_overrides(patch)
            reload_settings()
        return tuned

    @app.post("/api/search")
    def post_search(body: schemas.SearchRequest) -> dict[str, Any]:
        settings = _tuned(current_settings(), body)

        def work(bus: EventBus, job: Job) -> dict[str, Any]:
            stats = crawl.run_crawl(
                settings, bus, source_keys=body.sources, cancelled=job.cancel_requested.is_set
            )
            result: dict[str, Any] = {"crawl": stats.to_dict()}
            if body.then_match and not job.cancel_requested.is_set():
                try:
                    result["match"] = run_matching(
                        settings, client_for(settings), bus, cancelled=job.cancel_requested.is_set
                    )
                except ProfileMissing as exc:
                    bus.warn(str(exc), stage="score")
                    result["match"] = {"skipped": str(exc)}
            result["counts"] = store.counts()
            return result

        return {"task": manager.submit("search", work, label="Searching sources").summary()}

    @app.post("/api/match")
    def post_match(body: schemas.MatchRequest) -> dict[str, Any]:
        settings = current_settings()
        if body.rescore:
            settings = settings.model_copy(deep=True)
            settings.matching.rescore_existing = True

        def work(bus: EventBus, job: Job) -> dict[str, Any]:
            try:
                outcome = run_matching(
                    settings, client_for(settings), bus, cancelled=job.cancel_requested.is_set
                )
            except ProfileMissing as exc:
                raise RuntimeError(str(exc)) from exc
            outcome["counts"] = store.counts()
            return outcome

        return {
            "task": manager.submit("match", work, label="Matching against your profile").summary()
        }

    @app.get("/api/runs")
    def get_runs() -> dict[str, Any]:
        return {"runs": store.recent_runs()}

    # --- search history ----------------------------------------------------
    @app.get("/api/history")
    def get_history() -> dict[str, Any]:
        return {"runs": store.search_history()}

    @app.get("/api/history/{run_id}")
    def get_history_run(run_id: int) -> dict[str, Any]:
        runs = [run for run in store.search_history(limit=500) if run["id"] == run_id]
        if not runs:
            raise HTTPException(404, "That search is no longer in the history.")
        return {"run": runs[0], "results": store.run_results(run_id)}

    @app.delete("/api/history/{run_id}")
    def delete_history_run(run_id: int) -> dict[str, Any]:
        if not store.delete_run(run_id):
            raise HTTPException(404, "That search is no longer in the history.")
        return {"runs": store.search_history()}

    @app.delete("/api/history")
    def delete_history() -> dict[str, Any]:
        removed = store.clear_history()
        return {"removed": removed, "runs": store.search_history()}

    # --- job postings ------------------------------------------------------
    @app.post("/api/jobs/query")
    def post_jobs_query(body: schemas.JobFilter) -> dict[str, Any]:
        # "latest" is resolved here so the browser never has to guess which run
        # that is, and so it stays correct after a search finishes.
        run_id = body.run_id
        if body.run == "latest" and run_id is None:
            run_id = store.latest_run_id()
        elif body.run == "all":
            run_id = None

        return {
            "jobs": store.list_jobs(
                bands=body.bands or None,
                work_modes=body.work_modes or None,
                statuses=body.statuses or None,
                max_age_days=body.max_age_days,
                query=body.query.strip(),
                include_hidden=body.include_hidden,
                scored_only=body.scored_only,
                run_id=run_id,
                limit=max(1, min(body.limit, 500)),
                offset=max(0, body.offset),
            ),
            "counts": store.counts(),
            "run_id": run_id,
            "runs": store.search_history(limit=25),
        }

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: int) -> dict[str, Any]:
        job = store.get_job(job_id)
        if not job:
            raise HTTPException(404, "That posting is no longer stored.")
        cvs = store.list_cvs()
        primary = store.primary_cv()
        tailored = store.get_tailored(job_id, int(primary["id"])) if primary else {}
        if tailored:
            # So a reopened posting renders exactly like a freshly tailored one.
            tailored["prep_markdown"] = prep_markdown(tailored.get("prep_sheet") or {}, job)
        return {"job": job, "cvs": cvs, "tailored": tailored}

    @app.post("/api/jobs/{job_id}/hide")
    def post_job_hide(job_id: int, hidden: bool = True) -> dict[str, Any]:
        store.set_hidden(job_id, hidden)
        return {"job_id": job_id, "hidden": hidden}

    @app.post("/api/jobs/{job_id}/application")
    def post_job_application(job_id: int, body: schemas.ApplicationPatch) -> dict[str, Any]:
        if body.status not in APPLICATION_STATUSES:
            raise HTTPException(400, f"Status must be one of: {', '.join(APPLICATION_STATUSES)}")
        if not store.get_job(job_id):
            raise HTTPException(404, "That posting is no longer stored.")
        return {"application": store.set_application(job_id, status=body.status, notes=body.notes)}

    @app.get("/api/applications")
    def get_applications() -> dict[str, Any]:
        return {"applications": store.list_applications()}

    # --- tailoring ---------------------------------------------------------
    @app.post("/api/jobs/{job_id}/tailor")
    def post_tailor(job_id: int, body: schemas.TailorRequest) -> dict[str, Any]:
        settings = current_settings()
        job = store.get_job(job_id)
        if not job:
            raise HTTPException(404, "That posting is no longer stored.")

        record = store.get_cv(body.cv_id) if body.cv_id else store.primary_cv()
        if not record:
            raise HTTPException(400, "Upload a CV first — there is nothing to tailor.")

        def work(bus: EventBus, task: Job) -> dict[str, Any]:
            bus.stage_start("tailor", f"Rewriting for {job.get('title', 'this role')}")
            profile = store.get_profile().get("data") or {}
            result = tailor(
                client_for(settings),
                settings,
                profile=profile,
                cv_text=record.get("raw_text") or "",
                job=job,
                score={
                    "learnable_gaps": job.get("learnable_gaps") or [],
                    "hard_gaps": job.get("hard_gaps") or [],
                },
            )
            if result.moved_to_upskilling:
                bus.warn(
                    "Moved to upskilling because your CV does not evidence them: "
                    + ", ".join(result.moved_to_upskilling),
                    stage="tailor",
                )

            docx_path = ""
            if settings.tailor.output_format in {"docx", "both"}:
                bus.stage_start("export", "Writing the Word document")
                safe = _safe_name(f"{job.get('company', '')}-{job.get('title', '')}")
                target = exports_dir() / f"{safe}-{job_id}.docx"
                try:
                    docx_path = str(build_docx(result.content, profile, settings, target))
                except Exception as exc:  # noqa: BLE001
                    bus.warn(
                        f"DOCX export failed ({exc}). The Markdown version is still available."
                    )
                bus.stage_end("export", "Done" if docx_path else "Skipped")

            store.save_tailored(
                job_id=job_id,
                cv_id=int(record["id"]),
                content=result.content,
                prep_sheet=result.prep_sheet,
                markdown=result.markdown,
                docx_path=docx_path,
            )
            bus.stage_end("tailor", "Ready")
            payload = result.to_dict()
            payload.update(job_id=job_id, cv_id=int(record["id"]), docx_path=docx_path)
            payload["prep_markdown"] = prep_markdown(result.prep_sheet, job)
            return payload

        return {
            "task": manager.submit(
                "tailor",
                work,
                label=f"Tailoring for {job.get('company', '')}",
                meta={"job_id": job_id},
                single=False,
            ).summary()
        }

    @app.get("/api/jobs/{job_id}/tailor/download")
    def get_tailor_download(job_id: int, cv_id: int, kind: str = "docx") -> Response:
        record = store.get_tailored(job_id, cv_id)
        if not record:
            raise HTTPException(404, "Nothing has been tailored for this posting yet.")
        job = store.get_job(job_id)
        stem = _safe_name(f"{job.get('company', '')}-{job.get('title', '')}") or "cv"

        if kind == "markdown":
            return Response(
                record.get("markdown") or "",
                media_type="text/markdown; charset=utf-8",
                headers={"content-disposition": f'attachment; filename="{stem}.md"'},
            )
        if kind == "prep":
            return Response(
                prep_markdown(record.get("prep_sheet") or {}, job),
                media_type="text/markdown; charset=utf-8",
                headers={"content-disposition": f'attachment; filename="{stem}-prep.md"'},
            )

        path = record.get("docx_path") or ""
        if not path:
            raise HTTPException(404, "No Word document was produced for this posting.")
        resolved = _inside(exports_dir(), Path(path))
        if not resolved.is_file():
            raise HTTPException(404, "That file has been deleted.")
        return FileResponse(
            resolved,
            filename=f"{stem}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    # --- background tasks --------------------------------------------------
    @app.get("/api/tasks")
    def get_tasks() -> dict[str, Any]:
        return {"active": manager.active(), "recent": manager.recent()}

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        task = manager.get(task_id)
        if task is None:
            raise HTTPException(404, "That task is no longer tracked.")
        return {"task": task.summary(), "result": task.result, "error": task.error}

    @app.post("/api/tasks/{task_id}/cancel")
    def post_task_cancel(task_id: str) -> dict[str, Any]:
        if not manager.cancel(task_id):
            raise HTTPException(400, "That task has already finished.")
        return {"cancelled": True}

    @app.websocket("/ws/tasks/{task_id}")
    async def task_stream(websocket: WebSocket, task_id: str) -> None:
        await websocket.accept()
        task = manager.get(task_id)
        if task is None:
            await websocket.send_json({"type": "error", "message": "No such task."})
            await websocket.close()
            return

        loop = asyncio.get_running_loop()
        outbox: asyncio.Queue = asyncio.Queue()

        def forward(payload: dict[str, Any]) -> None:
            # Called from a worker thread; hop back onto the event loop.
            loop.call_soon_threadsafe(outbox.put_nowait, payload)

        stop = task.listen(forward)
        try:
            while True:
                payload = await outbox.get()
                await websocket.send_json(payload)
                if payload.get("type") == "done":
                    break
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            stop()
            try:
                await websocket.close()
            except RuntimeError:
                pass

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc) or exc.__class__.__name__})


def _submit_extract(cv_id: int) -> Job:
    settings = current_settings()

    def work(bus: EventBus, job: Job) -> dict[str, Any]:
        return profiling.extract_cv(cv_id, client_for(settings), settings, bus)

    return manager.submit("cv-extract", work, meta={"cv_id": cv_id}, single=False)


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in " -_" else " " for char in value)
    return "-".join(cleaned.split())[:80]
