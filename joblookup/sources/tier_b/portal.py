"""Config-driven Playwright portal adapter.

One Python class serves every login-walled portal. What differs between LinkedIn,
Naukri, Indeed and the rest is only selectors and URL shapes, and those live in
``portals/*.yaml``. When a portal changes its DOM the fix is a YAML edit, not a
code change — and **Test selectors** on the Sources screen tells you which line
to edit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlsplit

import yaml

from joblookup.models import RawJob
from joblookup.sources.base import (
    ConfigField,
    FetchContext,
    SetupGuide,
    SourceAdapter,
    SourceError,
    as_list,
)
from joblookup.sources.normalize import parse_date
from joblookup.sources.search_plan import execute_plan
from joblookup.sources.tier_b import browser
from joblookup.sources.tier_b.access import (
    AUTHENTICATED_MARKERS,
    CHALLENGES,
    LOGIN_WALLS,
    PUBLIC_PORTALS,
    blocked_url,
    portal_link,
    posting_details,
    public_jobs,
)
from joblookup.sources.tier_b.browser import TierBBlocked

PORTALS_DIR = Path(__file__).with_name("portals")

RISK_NOTICE = (
    "Portals such as LinkedIn restrict automated access. Sign-in does not grant permission "
    "to automate, and using a connector may result in account restrictions. Use it only "
    "where the portal permits your use. Passwords and two-factor codes are entered only "
    "on the portal's own website. Session cookies stay in a local browser profile. Public "
    "access may also be blocked. JobLookup does not bypass login or verification walls."
)


def load_portal_configs() -> dict[str, dict[str, Any]]:
    configs: dict[str, dict[str, Any]] = {}
    if not PORTALS_DIR.is_dir():
        return configs
    for path in sorted(PORTALS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise SourceError(f"{path.name} is not valid YAML: {exc}") from exc
        if data.get("key"):
            data["_file"] = str(path)
            configs[data["key"]] = data
    return configs


class PortalAdapter(SourceAdapter):
    tier = "b"
    rate_limit_s = 2.0

    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.key = spec["key"]
        self.name = spec.get("name", self.key.title())
        self.homepage = spec.get("homepage", "")
        self.login_url = spec.get("login_url", self.homepage)
        self.description = spec.get("description", "")
        self.selector_file = spec.get("_file", "")

    @property
    def supports_public(self) -> bool:
        return self.key in PUBLIC_PORTALS

    # --- gating ------------------------------------------------------------
    def config_fields(self) -> list[ConfigField]:
        return [
            ConfigField(
                "extra_terms",
                "Extra search terms",
                "list",
                placeholder="site reliability, platform engineer",
                help="Added to the titles from your profile when building the search URL.",
            )
        ]

    def is_configured(self, context: FetchContext) -> tuple[bool, str]:
        if context.settings.server.multi_user:
            return False, "Portal browser access is available only in a local workspace."
        if not context.settings.tier_b.enabled:
            return False, "Portal access is switched off."
        if not context.config.get("risk_ack"):
            return False, "The risk notice has not been accepted for this portal."
        if context.config.get("access_mode", "session") == "public":
            return (
                (True, "") if self.supports_public else (False, "This connector requires sign-in.")
            )
        state = browser.availability()
        if not state["browser_ready"]:
            return False, state["detail"]
        if not browser.has_session(context.settings, self.key):
            return False, f"Sign in to {self.name} to verify a browser session."
        return True, ""

    def setup_guide(self) -> SetupGuide:
        return SetupGuide(
            summary=(
                f"Optional access to {self.name} through your local browser session, "
                "a supported public listing page, or a manually imported posting. "
                "Availability depends on the portal's access rules and current layout."
            ),
            steps=[
                "Open Settings > Job sources > Job portals.",
                "Enable portal access and acknowledge the portal's restrictions.",
                "Choose Sign in and install browser support if prompted. "
                "Enter credentials only in the portal's browser window.",
                "The window closes once sign-in is verified. Include the portal in searches.",
                "Alternatively, try public access where offered, or import a posting manually.",
            ],
            links=[("Open the portal", self.homepage)] if self.homepage else [],
            note=RISK_NOTICE,
        )

    # --- fetch -------------------------------------------------------------
    def fetch(self, context: FetchContext) -> list[RawJob]:
        settings = context.settings
        ready, reason = self.is_configured(context)
        if not ready:
            raise TierBBlocked(f"{self.name}: {reason}")
        with browser.session_access(settings, self.key):
            browser.check_daily_cap(settings, self.key)
            browser.record_run(self.key)
            if context.config.get("access_mode", "session") == "public":
                return execute_plan(context, self.fetch_public)
            return execute_plan(context, self.fetch_session)

    def fetch_public(self, context: FetchContext) -> list[RawJob]:
        if context.cancelled():
            return []
        try:
            response = self.request(
                context, self.search_url(context, 0), headers={"accept": "text/html"}
            )
        except SourceError as exc:
            raise TierBBlocked(
                f"{self.name}: public access is unavailable ({exc}). "
                "Sign in or import a posting; no bypass was attempted."
            ) from exc
        jobs = public_jobs(self.spec, response.text, str(response.url))[: context.limit]
        for job in jobs[:3]:
            if context.cancelled():
                break
            try:
                detail_response = self.request(context, job.url, headers={"accept": "text/html"})
                details = posting_details(detail_response.text, str(detail_response.url))
            except (SourceError, TierBBlocked) as exc:
                context.stop_reason = str(exc)
                context.log(
                    f"{self.name}: full descriptions unavailable; keeping listing summaries. {exc}"
                )
                break
            if details.get("description"):
                job.description = details["description"]
                job.posted_at = job.posted_at or details.get("posted_at")
                job.raw["partial_description"] = False
        return jobs

    def authenticated(self, page: Any, browser_context: Any) -> bool:
        if blocked_url(page.url):
            return False
        host = urlsplit(page.url).hostname or ""
        root = (urlsplit(self.homepage).hostname or "").removeprefix("www.")
        if host != root and not host.endswith("." + root):
            return False
        for selector in [
            *AUTHENTICATED_MARKERS.get(self.key, []),
            "a[href*='logout']",
            "button[name='logout']",
        ]:
            if page.locator(selector).first.is_visible():
                return True
        if self.key == "linkedin":
            return any(
                cookie.get("name") == "li_at" and cookie.get("value")
                for cookie in browser_context.cookies([self.homepage])
            )
        return False

    def fetch_session(self, context: FetchContext) -> list[RawJob]:
        settings = context.settings

        selectors = self.spec.get("selectors") or {}
        for required in ("card", "title", "company"):
            if not selectors.get(required):
                raise SourceError(
                    f"{self.name} is missing the '{required}' selector in "
                    f"{Path(self.selector_file).name}."
                )

        max_pages = max(1, min(settings.tier_b.max_pages_per_run, 10))
        jobs: list[RawJob] = []
        playwright, browser_context = browser.launch_context(settings, self.key)
        try:
            page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
            for index in range(max_pages):
                if context.cancelled() or len(jobs) >= context.limit:
                    break
                url = self.search_url(context, index)
                context.log(f"{self.name}: page {index + 1}")
                response = page.goto(url, wait_until="domcontentloaded")
                browser.human_pause(settings)
                if response is not None and response.status in {401, 403, 429, 999}:
                    raise TierBBlocked(
                        f"{self.name} refused browser access. No retries or bypass attempted."
                    )

                if self._looks_logged_out(page):
                    browser.record_session(settings, self.key, authenticated=False)
                    raise TierBBlocked(
                        f"{self.name} showed a sign-in wall. The saved session has "
                        "expired — press Sign in on the Sources screen."
                    )

                found = self._harvest(page, selectors)
                if not found:
                    content = page.locator("body").inner_text(timeout=2000).casefold()
                    if not any(
                        message in content
                        for message in (
                            "no jobs found",
                            "no matching jobs",
                            "did not match any jobs",
                        )
                    ):
                        raise SourceError(
                            f"{self.name}: the page loaded but job cards were unreadable. "
                            "Import a posting or check the connector."
                        )
                    break
                jobs.extend(found)
        finally:
            try:
                browser_context.close()
            finally:
                playwright.stop()

        return jobs[: context.limit]

    # --- helpers -----------------------------------------------------------
    def search_url(self, context: FetchContext, page_index: int) -> str:
        template = self.spec.get("search_url", "")
        if not template:
            raise SourceError(f"{self.name} has no search_url in its YAML.")
        terms = [*context.queries, *as_list(context.config.get("extra_terms"))]
        keywords = terms[0] if terms else ""
        location = context.locations[0] if context.locations else ""
        page_size = int(self.spec.get("page_size", 25))
        return template.format(
            keywords=quote_plus(keywords),
            location=quote_plus(location),
            page=page_index + 1,
            start=page_index * page_size,
            days=context.recency_days,
            seconds=context.recency_days * 86400,
        )

    def _looks_logged_out(self, page: Any) -> bool:
        return blocked_url(page.url) or any(
            page.locator(selector).first.is_visible() for selector in (*CHALLENGES, *LOGIN_WALLS)
        )

    def _harvest(self, page: Any, selectors: dict[str, str]) -> list[RawJob]:
        cards = page.locator(selectors["card"])
        try:
            total = cards.count()
        except Exception as exc:  # noqa: BLE001
            raise SourceError(f"{self.name}: could not read the results list — {exc}") from exc

        jobs: list[RawJob] = []
        for index in range(total):
            card = cards.nth(index)
            title = _text(card, selectors.get("title"))
            company = _text(card, selectors.get("company"))
            if not title or not company:
                continue
            href = _attribute(card, selectors.get("link") or selectors.get("title"), "href")
            url = portal_link(self.homepage, href)
            if not url:
                continue
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=_attribute(card, selectors.get("id_from"), "data-job-id") or "",
                    title=title,
                    company=company,
                    location=_text(card, selectors.get("location")),
                    description=_text(card, selectors.get("summary")),
                    url=url,
                    posted_at=parse_date(
                        _attribute(card, selectors.get("posted"), "datetime")
                        or _text(card, selectors.get("posted"))
                    ),
                    raw={"portal": self.key, "access": "session", "partial_description": True},
                )
            )
        return jobs

    def test_selectors(self, context: FetchContext) -> dict[str, Any]:
        """Open one page and report how many nodes each selector matched.

        This is what turns "the portal returns nothing" from a debugging session
        into a two-minute YAML edit.
        """
        settings = context.settings
        selectors = self.spec.get("selectors") or {}
        results: dict[str, Any] = {"portal": self.key, "url": "", "selectors": {}}

        playwright, browser_context = browser.launch_context(settings, self.key)
        try:
            page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
            url = self.search_url(context, 0)
            results["url"] = url
            page.goto(url, wait_until="domcontentloaded")
            browser.human_pause(settings)
            results["logged_out"] = self._looks_logged_out(page)
            if results["logged_out"]:
                browser.record_session(settings, self.key, authenticated=False)
                raise TierBBlocked(f"{self.name}: access requires sign-in or verification.")

            card_count = 0
            try:
                card_count = page.locator(selectors.get("card", "body")).count()
            except Exception as exc:  # noqa: BLE001
                raise SourceError(f"{self.name}: the card selector is no longer valid.") from exc
            results["selectors"]["card"] = {
                "selector": selectors.get("card"),
                "matched": card_count,
            }

            if card_count:
                first = page.locator(selectors["card"]).first
                for field in ("title", "company", "location", "summary", "posted", "link"):
                    selector = selectors.get(field)
                    if not selector:
                        continue
                    try:
                        count = first.locator(selector).count()
                        sample = _text(first, selector)[:120]
                    except Exception as exc:  # noqa: BLE001
                        count, sample = 0, str(exc)[:120]
                    results["selectors"][field] = {
                        "selector": selector,
                        "matched": count,
                        "sample": sample,
                    }
        finally:
            try:
                browser_context.close()
            finally:
                playwright.stop()

        results["file"] = self.selector_file
        return results


def _text(scope: Any, selector: str | None) -> str:
    if not selector:
        return ""
    try:
        locator = scope.locator(selector).first
        if locator.count() == 0:
            return ""
        return (locator.inner_text(timeout=2000) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _attribute(scope: Any, selector: str | None, name: str) -> str:
    if not selector:
        return ""
    try:
        locator = scope.locator(selector).first
        if locator.count() == 0:
            return ""
        return (locator.get_attribute(name, timeout=2000) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def build_adapters() -> list[PortalAdapter]:
    return [PortalAdapter(spec) for spec in load_portal_configs().values()]
