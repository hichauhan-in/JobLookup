"""What every job source has in common.

A source adapter answers three questions: can it run right now, what does it
need from the user, and what postings does it have. Everything else — retries,
pacing, timeouts, the user agent — is handled here so an adapter is mostly the
shape of one API response.
"""

from __future__ import annotations

import ipaddress
import re
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx

from joblookup.config import Settings
from joblookup.models import RawJob

#: A source that has not answered in this many consecutive runs is worth telling
#: the user about, rather than silently contributing nothing.
FAILURE_PATIENCE = 3

#: Refuse an RSS feed larger than this rather than parse it into memory.
MAX_FEED_BYTES = 16 * 1024 * 1024

_DOCTYPE = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)

#: A redirect is a URL chosen by whoever we just called, so it gets the same
#: scrutiny as one the user typed. Enough hops for a real vendor, not enough
#: for a loop.
MAX_REDIRECTS = 5


def _is_private(host: str) -> bool:
    """Does this name or address point back at us or at the private network?

    Only literal addresses are resolved here. A hostname is left to DNS, which
    is the honest answer: we cannot pin what a name will resolve to at connect
    time without doing the lookup ourselves, and the addresses that matter for
    a metadata-service or loopback attack are almost always given literally.
    """
    bare = host.strip().strip("[]").split("%", 1)[0]
    if bare.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        address = ipaddress.ip_address(bare)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def check_outbound(url: str) -> None:
    """Refuse to fetch anything that is not a public web address.

    Sources are third parties, and a third party can answer with a redirect.
    Following one to ``169.254.169.254`` or back to our own API would turn every
    enabled feed into a way to read this machine, so every URL is checked, not
    just the ones the user typed.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise SourceError(f"Refusing to fetch a {parts.scheme or 'schemeless'} address.")
    if parts.username or parts.password:
        raise SourceError("Refusing a URL that carries credentials in the host.")
    host = parts.hostname or ""
    if not host:
        raise SourceError("That address has no host.")
    if _is_private(host):
        raise SourceError(f"Refusing to fetch {host}, which is on this machine or network.")


@dataclass(slots=True)
class ConfigField:
    """One thing the user can set for a source, rendered by the Sources screen."""

    key: str
    label: str
    kind: str = "text"  # text | password | list | number | boolean
    placeholder: str = ""
    help: str = ""
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "placeholder": self.placeholder,
            "help": self.help,
            "required": self.required,
        }


@dataclass(slots=True)
class SetupGuide:
    """How to get this source working, written for someone who has never seen it.

    Lives on the adapter rather than in the UI because the person who knows that
    USAJOBS wants your email as the user agent is the person writing the adapter.
    """

    summary: str = ""
    steps: list[str] = field(default_factory=list)
    #: ``(label, url)`` pairs shown as buttons under the steps.
    links: list[tuple[str, str]] = field(default_factory=list)
    #: Concrete examples, ``(what_you_see, what_to_enter)``.
    examples: list[tuple[str, str]] = field(default_factory=list)
    #: ``(label, value)`` pairs answering "what do I actually get from this?".
    #: A source needing no setup has no steps, so without these its help dialog
    #: would be a title and one line, which is what an empty dialog looks like.
    facts: list[tuple[str, str]] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "steps": list(self.steps),
            "links": [{"label": label, "url": url} for label, url in self.links],
            "examples": [{"seen": seen, "enter": enter} for seen, enter in self.examples],
            "facts": [{"label": label, "value": value} for label, value in self.facts],
            "note": self.note,
        }


@dataclass
class FetchContext:
    """Everything an adapter needs to do one run."""

    settings: Settings
    #: Per-source options the user set, e.g. the list of Greenhouse slugs.
    config: dict[str, Any] = field(default_factory=dict)
    #: What the profile says we are looking for, so keyed APIs can pass a query.
    queries: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    #: Reads a secret by name. Never a literal value in a config file.
    secret: Callable[[str], str] = lambda name: ""
    log: Callable[[str], None] = lambda message: None
    cancelled: Callable[[], bool] = lambda: False
    search_report: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""

    @property
    def recency_days(self) -> int:
        return self.settings.search.recency_days

    @property
    def limit(self) -> int:
        return self.settings.search.max_jobs_per_source


class RateLimiter:
    """A shared floor on request frequency, per host.

    Politeness is not optional: a personal tool hammering a free API is how free
    APIs stop being free.
    """

    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, key: str, interval: float) -> None:
        if interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            earliest = self._last.get(key, 0.0) + interval
            delay = max(0.0, earliest - now)
            self._last[key] = now + delay
        if delay:
            time.sleep(delay)


_limiter = RateLimiter()


class SourceAdapter(ABC):
    """One place jobs come from."""

    key: str = ""
    name: str = ""
    #: 'a' public API · 'ats' company board · 'b' logged-in portal
    tier: str = "a"
    homepage: str = ""
    requires_key: bool = False
    #: Extra pacing beyond the global floor, when a source asks for it.
    rate_limit_s: float = 0.0
    description: str = ""

    # --- readiness ---------------------------------------------------------
    def is_configured(self, context: FetchContext) -> tuple[bool, str]:
        """Return ``(ready, reason_if_not)``. Free sources are always ready."""
        return True, ""

    def config_fields(self) -> list[ConfigField]:
        return []

    def setup_guide(self) -> SetupGuide:
        """What the user has to do before this source can run."""
        return SetupGuide(
            summary=self.description or "This source needs no setup.",
            note="No account and no key. Turn it on and the next search includes it.",
            links=[("Visit the site", self.homepage)] if self.homepage else [],
        )

    # --- fetching ----------------------------------------------------------
    @abstractmethod
    def fetch(self, context: FetchContext) -> list[RawJob]:
        """Return whatever postings this source currently has.

        Filtering by recency and relevance happens downstream — an adapter's job
        is to hand over what the source said, not to have opinions about it.
        """

    # --- helpers for subclasses -------------------------------------------
    def get_json(
        self,
        context: FetchContext,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        json_body: Any = None,
    ) -> Any:
        response = self.request(
            context, url, params=params, headers=headers, method=method, json_body=json_body
        )
        try:
            return response.json()
        except ValueError as exc:
            raise SourceError(
                f"{self.name} returned something that is not JSON "
                f"({response.headers.get('content-type', 'unknown type')})."
            ) from exc

    def get_xml(
        self,
        context: FetchContext,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> ElementTree.Element:
        """Parse an RSS feed, refusing any document that declares XML entities.

        Every entity attack — external entity disclosure and the expansion bombs
        alike — needs a DOCTYPE to declare the entity first, so refusing the
        declaration closes the whole class without swapping in another parser.
        Python's own parser does expand internal entities, so this is not
        theoretical.
        """
        response = self.request(
            context,
            url,
            params=params,
            headers={"accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.5"},
        )
        body = response.content
        if len(body) > MAX_FEED_BYTES:
            raise SourceError(
                f"{self.name} returned {len(body) // 1024 // 1024} MB of XML, which is far "
                "more than a job feed should be. Refusing to parse it."
            )
        text = response.text
        if _DOCTYPE.search(text):
            raise SourceError(
                f"{self.name} returned XML containing a document type or entity "
                "declaration. A job feed has no reason to, so it was not parsed."
            )
        try:
            return ElementTree.fromstring(text)
        except ElementTree.ParseError as exc:
            raise SourceError(f"{self.name} returned XML that will not parse: {exc}") from exc

    def request(
        self,
        context: FetchContext,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        json_body: Any = None,
        allow_statuses: frozenset[int] | set[int] = frozenset(),
    ) -> httpx.Response:
        search = context.settings.search
        merged = {
            "user-agent": search.user_agent,
            "accept": "application/json, text/plain;q=0.8, */*;q=0.5",
            **(headers or {}),
        }

        with httpx.Client(timeout=search.http_timeout_s, follow_redirects=False) as client:
            outgoing = client.build_request(
                method, url, params=params, headers=merged, json=json_body
            )
            for hop in range(MAX_REDIRECTS + 1):
                target = str(outgoing.url)
                check_outbound(target)
                _limiter.wait(
                    _host_of(target), max(search.min_request_interval_s, self.rate_limit_s)
                )
                try:
                    response = client.send(outgoing)
                except httpx.RequestError as exc:
                    raise SourceError(
                        f"Could not reach {_host_of(target)} ({type(exc).__name__})."
                    ) from exc
                following = response.next_request
                if following is None:
                    break
                if hop == MAX_REDIRECTS:
                    raise SourceError(f"{self.name} exceeded the redirect limit.")
                origin = (outgoing.url.scheme, outgoing.url.host, outgoing.url.port)
                destination = (following.url.scheme, following.url.host, following.url.port)
                if origin != destination:
                    if outgoing.method not in {"GET", "HEAD"}:
                        raise SourceError(
                            "A source tried to redirect a submitted request to another host."
                        )
                    for secret_header in ("authorization", "api-key", "x-api-key", "cookie"):
                        following.headers.pop(secret_header, None)
                outgoing = following

        if response.status_code in allow_statuses:
            return response
        if response.status_code == 429:
            raise SourceError(
                f"{self.name} is rate limiting us. Raise search.min_request_interval_s "
                "or run the search less often."
            )
        if response.status_code in (401, 403):
            if self.tier == "b":
                raise SourceError(
                    f"{self.name} blocked portal access (HTTP {response.status_code})."
                )
            raise SourceError(
                f"{self.name} refused the request ({response.status_code}). "
                "Check the API key on the Sources screen."
            )
        if response.status_code >= 400:
            raise SourceError(f"{self.name} returned HTTP {response.status_code}.")
        return response


class SourceError(RuntimeError):
    """A source failed in a way worth showing the user."""


def _host_of(url: str) -> str:
    without_scheme = url.split("://", 1)[-1]
    return without_scheme.split("/", 1)[0].lower()


def as_list(value: Any) -> list[str]:
    """Config values arrive as a list, a comma-separated string, or nothing."""
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]
