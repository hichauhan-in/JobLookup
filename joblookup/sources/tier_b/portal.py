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
from urllib.parse import quote_plus, urljoin

import yaml

from joblookup.models import RawJob
from joblookup.sources.base import (
    ConfigField,
    FetchContext,
    SetupGuide,
    SourceAdapter,
    SourceError,
)
from joblookup.sources.tier_b import browser
from joblookup.sources.tier_b.browser import TierBBlocked, TierBDisabled

PORTALS_DIR = Path(__file__).with_name("portals")

RISK_NOTICE = (
    "This portal prohibits automated access in its terms of service. Using it can get "
    "your account restricted or permanently banned, and in some places carries further "
    "legal exposure. JobLookup never sees your password, because you sign in yourself in "
    "a visible browser window, but that does not remove the risk. Start with the public "
    "APIs and the ATS boards; they will likely give you more good postings than this "
    "ever will."
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

    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.key = spec["key"]
        self.name = spec.get("name", self.key.title())
        self.homepage = spec.get("homepage", "")
        self.login_url = spec.get("login_url", self.homepage)
        self.description = spec.get("description", "")
        self.selector_file = spec.get("_file", "")

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
        if not context.settings.tier_b.enabled:
            return False, "Logged-in portal automation is switched off in Settings."
        if not context.config.get("risk_ack"):
            return False, "The risk notice has not been accepted for this portal."
        state = browser.availability()
        if not state["browser_ready"]:
            return False, state["detail"]
        if not browser.has_session(context.settings, self.key):
            return False, f"No saved session. Press Sign in for {self.name} on this screen."
        return True, ""

    def setup_guide(self) -> SetupGuide:
        return SetupGuide(
            summary=(
                f"{self.name} has no public API, so the only way in is a real browser that "
                "is already signed in as you. This is the one part of JobLookup that "
                "carries a genuine risk to your account, and it is off until you turn it on."
            ),
            steps=[
                "Turn on the master switch at the top of this section.",
                "Install Playwright and Chromium if you have not already. It is a large "
                "download and is never fetched unless you ask for it.",
                "Turn on Risk for this portal and read the notice you are accepting.",
                "Press Sign in. A normal browser window opens on the portal's own login "
                "page. Sign in exactly as you usually would, including any two-factor step.",
                "Close that window. The session cookie stays in a local profile folder.",
                "Turn the portal on. It will now be included in searches.",
            ],
            links=[("Open the portal", self.homepage)] if self.homepage else [],
            note=(
                "JobLookup never sees your password: you type it into the portal's own "
                "page, not into JobLookup. There is no CAPTCHA solving and no two-factor "
                "circumvention. Requests are paced with randomised human-scale delays and "
                "capped per day. None of that removes the risk that the portal notices and "
                "restricts your account, which is why the public APIs and company boards "
                "are the better place to spend your effort."
            ),
        )

    # --- fetch -------------------------------------------------------------
    def fetch(self, context: FetchContext) -> list[RawJob]:
        settings = context.settings
        if not settings.tier_b.enabled:
            raise TierBDisabled("Logged-in portal automation is switched off.")
        if not context.config.get("risk_ack"):
            raise TierBBlocked(f"{self.name}: accept the risk notice before running.")
        if not browser.has_session(settings, self.key):
            raise TierBBlocked(f"{self.name}: no saved session. Sign in first.")
        browser.check_daily_cap(settings, self.key)

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
            browser.record_run(self.key)
            page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
            for index in range(max_pages):
                if context.cancelled() or len(jobs) >= context.limit:
                    break
                url = self.search_url(context, index)
                context.log(f"{self.name}: page {index + 1}")
                page.goto(url, wait_until="domcontentloaded")
                browser.human_pause(settings)

                if self._looks_logged_out(page):
                    raise TierBBlocked(
                        f"{self.name} showed a sign-in wall. The saved session has "
                        "expired — press Sign in on the Sources screen."
                    )

                found = self._harvest(page, selectors)
                if not found:
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
        terms = [*context.queries, *(context.config.get("extra_terms") or [])]
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
        for selector in self.spec.get("logged_out_markers") or []:
            try:
                if page.locator(selector).count() > 0:
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

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
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=_attribute(card, selectors.get("id_from"), "data-job-id") or "",
                    title=title,
                    company=company,
                    location=_text(card, selectors.get("location")),
                    description=_text(card, selectors.get("summary")),
                    url=urljoin(self.homepage, href) if href else "",
                    posted_at=_text(card, selectors.get("posted")),
                    raw={"portal": self.key},
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

            card_count = 0
            try:
                card_count = page.locator(selectors.get("card", "body")).count()
            except Exception as exc:  # noqa: BLE001
                results["selectors"]["card"] = {
                    "selector": selectors.get("card"),
                    "error": str(exc),
                }
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
