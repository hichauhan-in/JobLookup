"""Public-page parsing and explicit portal access-wall detection."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from joblookup.models import RawJob
from joblookup.sources.base import SourceError
from joblookup.sources.normalize import parse_date
from joblookup.sources.tier_b.browser import TierBBlocked

PUBLIC_PORTALS = frozenset({"linkedin", "indeed", "naukri", "foundit", "dice", "wellfound"})
AUTHENTICATED_MARKERS = {
    "linkedin": ["button.global-nav__primary-link-me-menu-trigger", ".global-nav__me-photo"],
    "naukri": ["a[href*='/mnjuser/profile']", ".nI-gNb-drawer__icon-img"],
    "indeed": ["a[href*='/account/logout']", "[data-testid='account-menu-avatar']"],
    "glassdoor": ["button[data-test='user-profile-menu']"],
    "foundit": ["a[href*='/seeker/profile']"],
    "dice": ["a[href*='/dashboard/profiles']"],
    "wellfound": ["a[href*='/profile/edit']"],
    "instahyre": ["a[href='/candidate/profile/']"],
    "cutshort": ["a[href='/profile/edit']"],
}
CHALLENGES = (
    "#challenge-running",
    "#px-captcha",
    "#captcha-internal",
    "iframe[src*='captcha']",
    "iframe[src*='challenge']",
    "div.g-recaptcha",
)
LOGIN_WALLS = (
    "div.authwall",
    "form.login__form",
    "form#new_user",
    "input[type='password']",
    "#HardsellOverlay",
    "form[data-test='emailForm']",
)


def blocked_url(url: str) -> bool:
    path = urlsplit(url).path.casefold()
    return any(
        part in path
        for part in (
            "/login",
            "/signin",
            "/sign-in",
            "/authwall",
            "/checkpoint",
            "/challenge",
            "/captcha",
        )
    )


def portal_link(base: str, href: str) -> str:
    if not href:
        return ""
    result = urljoin(base, href)
    try:
        parts = urlsplit(result)
        host = urlsplit(base).hostname or ""
        root = host.removeprefix("www.")
        if parts.scheme not in {"http", "https"} or parts.username or parts.password:
            return ""
        if parts.hostname != root and not (parts.hostname or "").endswith("." + root):
            return ""
    except ValueError:
        return ""
    return result


def readable_page(html: str, final_url: str) -> BeautifulSoup:
    if len(html) > 4 * 1024 * 1024:
        raise SourceError("The portal returned an unusually large page.")
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True).casefold() if soup.title else ""
    if (
        blocked_url(final_url)
        or any(
            phrase in title
            for phrase in (
                "verify you are",
                "security check",
                "just a moment",
                "access denied",
                "sign in",
                "log in",
            )
        )
        or any(soup.select_one(selector) for selector in CHALLENGES)
    ):
        raise TierBBlocked(
            "Public access requires sign-in or verification. "
            "No bypass was attempted; use sign-in or import a posting."
        )
    return soup


def public_jobs(spec: dict[str, Any], html: str, final_url: str) -> list[RawJob]:
    soup = readable_page(html, final_url)
    selectors = spec.get("selectors") or {}
    cards = soup.select(selectors.get("card", "[data-job-card]"))
    if not cards:
        if any(soup.select_one(selector) for selector in LOGIN_WALLS):
            raise TierBBlocked("The portal requires sign-in. Public access stopped.")
        content = soup.get_text(" ", strip=True).casefold()
        if any(
            phrase in content
            for phrase in ("no jobs found", "no matching jobs", "did not match any jobs")
        ):
            return []
        raise SourceError(
            "No job cards were readable on the public page. "
            "The layout may have changed; import a posting instead."
        )
    jobs = []
    seen = set()
    for card in cards:

        def element(field, card=card):
            selector = selectors.get(field)
            return card.select_one(selector) if selector else None

        def text(field):
            node = element(field)
            return node.get_text(" ", strip=True) if node else ""

        link = element("link")
        url = portal_link(spec["homepage"], str(link.get("href") or "") if link else "")
        name, company = text("title"), text("company")
        if not url or not name or not company or url in seen:
            continue
        seen.add(url)
        posted = element("posted")
        date = str(posted.get("datetime") or "") if posted else ""
        jobs.append(
            RawJob(
                source_key=spec["key"],
                title=name,
                company=company,
                location=text("location"),
                description=text("summary"),
                url=url,
                posted_at=parse_date(date or text("posted")),
                raw={"portal": spec["key"], "access": "public", "partial_description": True},
            )
        )
    if cards and not jobs:
        raise SourceError(
            "The portal page did not contain complete job cards. "
            "Import the posting details manually."
        )
    return jobs


def posting_details(html: str, final_url: str) -> dict[str, Any]:
    soup = readable_page(html, final_url)
    for script in soup.select("script[type='application/ld+json']"):
        try:
            payload = json.loads(script.get_text())
        except (ValueError, TypeError):
            continue
        entries = payload if isinstance(payload, list) else [payload]
        for entry in entries[:100]:
            if not isinstance(entry, dict):
                continue
            graph = entry.get("@graph") or []
            for item in [entry, *(graph if isinstance(graph, list) else [])][:100]:
                if not isinstance(item, dict):
                    continue
                kind = item.get("@type")
                if kind != "JobPosting" and not (isinstance(kind, list) and "JobPosting" in kind):
                    continue
                description = item.get("description")
                if isinstance(description, str) and description.strip():
                    return {
                        "description": BeautifulSoup(description, "html.parser").get_text(
                            "\n", strip=True
                        ),
                        "posted_at": parse_date(item.get("datePosted")),
                    }
    description = soup.select_one(
        ".show-more-less-html__markup, #jobDescriptionText, [itemprop='description']"
    )
    if description:
        return {"description": description.get_text("\n", strip=True), "posted_at": None}
    if any(soup.select_one(selector) for selector in LOGIN_WALLS):
        raise TierBBlocked("The full description requires sign-in; public detail access stopped.")
    return {}
