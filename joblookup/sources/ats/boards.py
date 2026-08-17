"""Company applicant-tracking boards.

Companies publish their own openings as public JSON on Greenhouse, Lever, Ashby,
Workable, Recruitee and SmartRecruiters. These are the freshest and cleanest
postings available anywhere: no aggregator lag, no login, full descriptions, and
the apply link goes straight to the employer.

This is where it is worth spending your time. Open the careers page of a company
you want, copy the slug out of the URL, and add it on the Sources screen. A slug
that no longer exists simply 404s and is skipped.
"""

from __future__ import annotations

import re
from typing import Any

from joblookup.models import RawJob
from joblookup.sources.base import (
    ConfigField,
    FetchContext,
    SetupGuide,
    SourceAdapter,
    SourceError,
    as_list,
)


def _company_name(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title()


class _BoardAdapter(SourceAdapter):
    """Shared loop: walk the configured companies, skip the ones that fail."""

    tier = "ats"
    rate_limit_s = 0.6
    #: Where the company name sits in the careers page address.
    address_shape = ""
    #: ``(address you see, what to enter)`` pairs, shown in the help dialog.
    examples: tuple[tuple[str, str], ...] = ()

    def config_fields(self) -> list[ConfigField]:
        return [
            ConfigField(
                "slugs",
                "Companies to watch",
                "list",
                placeholder=", ".join(enter for _, enter in self.examples[:3]),
                help=(
                    f"The company's short name from its careers page address "
                    f"({self.address_shape}). Separate several with commas. "
                    "Press the ? above for worked examples."
                ),
                required=True,
            )
        ]

    def setup_guide(self) -> SetupGuide:
        return SetupGuide(
            summary=(
                "Add the companies you want to watch. Each publishes its own openings, so "
                "you get them straight from the employer with no aggregator in between - "
                "fresher, complete descriptions, and the apply link goes to them directly."
            ),
            steps=[
                "Open the careers page of a company you would like to work for.",
                f"Look at the address bar. If it looks like {self.address_shape}, "
                f"this is the right board for that company.",
                "Take the company's short name out of that address and enter it below.",
                "Add as many companies as you like, separated by commas.",
            ],
            examples=list(self.examples),
            note=(
                "No account and no key. If a company has moved to a different board it "
                "simply returns nothing and is skipped, so try the same name on the other "
                "boards. Nothing you enter here is sent anywhere except to that board."
            ),
        )

    def is_configured(self, context: FetchContext) -> tuple[bool, str]:
        if not as_list(context.config.get("slugs")):
            return False, "Add at least one company."
        return True, ""

    def fetch(self, context: FetchContext) -> list[RawJob]:
        slugs = as_list(context.config.get("slugs"))
        if not slugs:
            raise SourceError("No companies are configured for this board.")

        jobs: list[RawJob] = []
        failures: list[str] = []
        for slug in slugs:
            if context.cancelled() or len(jobs) >= context.limit:
                break
            try:
                found = self.fetch_company(slug, context)
            except Exception as exc:  # noqa: BLE001
                # One dead company must not cost the whole board.
                failures.append(f"{slug}: {exc}")
                context.log(f"{self.name}: {slug} failed — {exc}")
                continue
            context.log(f"{self.name}: {slug} → {len(found)}")
            jobs.extend(found)

        if not jobs and failures:
            raise SourceError(
                f"None of the companies returned anything. First problem — {failures[0]}"
            )
        return jobs[: context.limit]

    def fetch_company(self, slug: str, context: FetchContext) -> list[RawJob]:
        raise NotImplementedError


class Greenhouse(_BoardAdapter):
    key = "greenhouse"
    name = "Greenhouse boards"
    homepage = "https://boards.greenhouse.io"
    description = "Widely used by mid-size and large tech companies."
    address_shape = "boards.greenhouse.io/<company>"
    examples = (
        ("https://boards.greenhouse.io/stripe", "stripe"),
        ("https://job-boards.greenhouse.io/figma", "figma"),
        ("https://boards.greenhouse.io/databricks", "databricks"),
    )

    def fetch_company(self, slug: str, context: FetchContext) -> list[RawJob]:
        payload = self.get_json(
            context,
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            params={"content": "true"},
        )
        jobs: list[RawJob] = []
        for item in payload.get("jobs") or []:
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=str(item.get("id", "")),
                    title=item.get("title") or "",
                    company=_company_name(slug),
                    location=(item.get("location") or {}).get("name", ""),
                    description=item.get("content") or "",
                    url=item.get("absolute_url") or "",
                    posted_at=item.get("first_published") or item.get("updated_at"),
                    raw={"board": slug},
                )
            )
        return jobs


class Lever(_BoardAdapter):
    key = "lever"
    name = "Lever boards"
    homepage = "https://jobs.lever.co"
    description = "Common at startups and scale-ups."
    address_shape = "jobs.lever.co/<company>"
    examples = (
        ("https://jobs.lever.co/spotify", "spotify"),
        ("https://jobs.lever.co/palantir", "palantir"),
    )

    def fetch_company(self, slug: str, context: FetchContext) -> list[RawJob]:
        payload = self.get_json(
            context, f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"}
        )
        if not isinstance(payload, list):
            return []
        jobs: list[RawJob] = []
        for item in payload:
            categories = item.get("categories") or {}
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=str(item.get("id", "")),
                    title=item.get("text") or "",
                    company=_company_name(slug),
                    location=categories.get("location") or "",
                    description=item.get("descriptionPlain") or item.get("description") or "",
                    url=item.get("hostedUrl") or "",
                    apply_url=item.get("applyUrl") or "",
                    posted_at=item.get("createdAt"),
                    work_mode=(categories.get("workplaceType") or "").lower(),
                    employment=categories.get("commitment") or "",
                    raw={"board": slug, "team": categories.get("team", "")},
                )
            )
        return jobs


class Ashby(_BoardAdapter):
    key = "ashby"
    name = "Ashby boards"
    homepage = "https://jobs.ashbyhq.com"
    description = "Newer ATS, popular with well-funded startups."
    address_shape = "jobs.ashbyhq.com/<company>"
    examples = (
        ("https://jobs.ashbyhq.com/linear", "linear"),
        ("https://jobs.ashbyhq.com/ramp", "ramp"),
    )

    def fetch_company(self, slug: str, context: FetchContext) -> list[RawJob]:
        payload = self.get_json(
            context,
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            params={"includeCompensation": "true"},
        )
        jobs: list[RawJob] = []
        for item in payload.get("jobs") or []:
            compensation = item.get("compensation") or {}
            summary = (compensation.get("summaryComponents") or [{}])[0]
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=str(item.get("id", "")),
                    title=item.get("title") or "",
                    company=payload.get("name") or _company_name(slug),
                    location=item.get("location") or "",
                    description=item.get("descriptionPlain") or item.get("descriptionHtml") or "",
                    url=item.get("jobUrl") or "",
                    apply_url=item.get("applyUrl") or "",
                    posted_at=item.get("publishedAt"),
                    work_mode="remote" if item.get("isRemote") else "",
                    employment=item.get("employmentType") or "",
                    salary_min=summary.get("minValue"),
                    salary_max=summary.get("maxValue"),
                    salary_currency=summary.get("currencyCode") or "",
                    raw={"board": slug, "department": item.get("department", "")},
                )
            )
        return jobs


class Workable(_BoardAdapter):
    key = "workable"
    name = "Workable boards"
    homepage = "https://www.workable.com"
    description = "Very broad adoption outside tech as well as inside it."
    address_shape = "apply.workable.com/<company>"
    examples = (
        ("https://apply.workable.com/blueground", "blueground"),
        ("https://apply.workable.com/orfium", "orfium"),
        ("https://apply.workable.com/skroutz", "skroutz"),
    )

    def fetch_company(self, slug: str, context: FetchContext) -> list[RawJob]:
        payload = self.get_json(
            context,
            f"https://apply.workable.com/api/v1/widget/accounts/{slug}",
            params={"details": "true"},
        )
        company = (payload.get("name") or _company_name(slug)).strip()
        jobs: list[RawJob] = []
        for item in payload.get("jobs") or []:
            location = ", ".join(
                part for part in (item.get("city"), item.get("state"), item.get("country")) if part
            )
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=str(item.get("shortcode", "")),
                    title=item.get("title") or "",
                    company=company,
                    location=location or item.get("location") or "",
                    description=item.get("description") or "",
                    url=item.get("url") or item.get("application_url") or "",
                    apply_url=item.get("application_url") or "",
                    posted_at=item.get("published_on") or item.get("created_at"),
                    work_mode="remote" if item.get("telecommuting") else "",
                    employment=item.get("employment_type") or "",
                    raw={"board": slug, "department": item.get("department", "")},
                )
            )
        return jobs


class Recruitee(_BoardAdapter):
    key = "recruitee"
    name = "Recruitee boards"
    homepage = "https://recruitee.com"
    description = "Popular across Europe, especially the Netherlands and Germany."
    address_shape = "<company>.recruitee.com"
    examples = (
        ("https://bunq.recruitee.com", "bunq"),
        ("https://framestore.recruitee.com", "framestore"),
        ("https://livestorm.recruitee.com", "livestorm"),
    )

    def fetch_company(self, slug: str, context: FetchContext) -> list[RawJob]:
        payload = self.get_json(context, f"https://{slug}.recruitee.com/api/offers/")
        jobs: list[RawJob] = []
        for item in payload.get("offers") or []:
            location = ", ".join(part for part in (item.get("city"), item.get("country")) if part)
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=str(item.get("id", "")),
                    title=item.get("title") or "",
                    company=item.get("company_name") or _company_name(slug),
                    location=location or item.get("location") or "",
                    description=item.get("description") or item.get("requirements") or "",
                    url=item.get("careers_url") or item.get("careers_apply_url") or "",
                    apply_url=item.get("careers_apply_url") or "",
                    posted_at=item.get("published_at") or item.get("created_at"),
                    work_mode="remote" if item.get("remote") else "",
                    employment=item.get("employment_type_code") or "",
                    raw={"board": slug, "department": item.get("department", "")},
                )
            )
        return jobs


class SmartRecruiters(_BoardAdapter):
    key = "smartrecruiters"
    name = "SmartRecruiters boards"
    homepage = "https://www.smartrecruiters.com"
    description = "Used by large enterprises; listings are paged."
    address_shape = "careers.smartrecruiters.com/<Company>"
    examples = (
        ("https://careers.smartrecruiters.com/Visa", "Visa"),
        ("https://careers.smartrecruiters.com/ClarivateAnalytics", "ClarivateAnalytics"),
    )

    def setup_guide(self) -> SetupGuide:
        guide = super().setup_guide()
        guide.note = (
            "SmartRecruiters is the one board where capitalisation matters: enter the name "
            "exactly as it appears in the address, usually starting with a capital letter. "
            + guide.note
        )
        return guide

    def fetch_company(self, slug: str, context: FetchContext) -> list[RawJob]:
        jobs: list[RawJob] = []
        offset = 0
        while offset < 300 and len(jobs) < context.limit:
            payload = self.get_json(
                context,
                f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                params={"limit": 100, "offset": offset},
            )
            items = payload.get("content") or []
            if not items:
                break
            for item in items:
                location = item.get("location") or {}
                place = ", ".join(
                    part
                    for part in (
                        location.get("city"),
                        location.get("region"),
                        location.get("country"),
                    )
                    if part
                )
                jobs.append(
                    RawJob(
                        source_key=self.key,
                        source_job_id=str(item.get("id", "")),
                        title=item.get("name") or "",
                        company=(item.get("company") or {}).get("name") or _company_name(slug),
                        # The list endpoint carries no description. Fetching one
                        # detail request per posting would be hundreds of calls
                        # against a shared API, so the summary line is used and
                        # the full text is one click away on the posting itself.
                        location=place,
                        description=item.get("jobAd", {})
                        .get("sections", {})
                        .get("jobDescription", {})
                        .get("text", "")
                        or item.get("name")
                        or "",
                        url=item.get("ref")
                        or f"https://jobs.smartrecruiters.com/{slug}/{item.get('id', '')}",
                        posted_at=item.get("releasedDate") or item.get("createdOn"),
                        work_mode="remote" if location.get("remote") else "",
                        employment=(item.get("typeOfEmployment") or {}).get("label", ""),
                        raw={
                            "board": slug,
                            "department": (item.get("department") or {}).get("label", ""),
                        },
                    )
                )
            offset += len(items)
        return jobs


class Workday(_BoardAdapter):
    """The board most large employers use, and the only one addressed by URL.

    A Workday careers site is identified by three things that cannot be guessed
    from a company name — the host shard (``wd5``), the tenant and the site name
    — so this adapter takes the address itself and pulls them out. It also costs
    one extra request per posting, because Workday's listing endpoint returns
    titles without descriptions.
    """

    key = "workday"
    name = "Workday sites"
    homepage = "https://www.myworkdayjobs.com"
    description = "Used by most large enterprises. Paste the careers page address as-is."
    address_shape = "<company>.wd<N>.myworkdayjobs.com/<SiteName>"
    rate_limit_s = 0.5
    examples = (
        (
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        ),
        (
            "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site",
            "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site",
        ),
    )

    def config_fields(self) -> list[ConfigField]:
        return [
            ConfigField(
                "slugs",
                "Careers page addresses",
                "list",
                placeholder="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
                help=(
                    "Paste the whole address of the company's Workday careers page. "
                    "Unlike the other boards there is no short name to extract - the "
                    "address itself is the identifier. One per line."
                ),
                required=True,
            ),
            ConfigField(
                "descriptions_per_company",
                "Descriptions to fetch per company",
                "number",
                placeholder="25",
                help=(
                    "Workday sends titles and descriptions separately, so each posting "
                    "costs a second request. Raise this for more thorough matching and a "
                    "slower search; lower it for the reverse. Default 25."
                ),
            ),
        ]

    def setup_guide(self) -> SetupGuide:
        return SetupGuide(
            summary=(
                "Workday is what most large employers run their careers site on, so this "
                "is the board that reaches the big names. It is the one place you paste "
                "the whole address rather than a short company name."
            ),
            steps=[
                "Open the company's careers page and look for myworkdayjobs.com in the address.",
                "Copy the address as far as the site name, e.g. "
                "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
                "Paste it below. Anything after the site name, and any /en-US/ language "
                "part, is ignored, so a copied link from the middle of a search still works.",
                "Add as many companies as you like, one per line.",
            ],
            examples=list(self.examples),
            note=(
                "Workday is slower than the other boards because each posting needs a "
                "second request to fetch its description. The 'Descriptions to fetch' "
                "setting is the trade-off dial. No account and no key."
            ),
        )

    def fetch_company(self, slug: str, context: FetchContext) -> list[RawJob]:
        host, tenant, site = parse_workday_url(slug)
        base = f"https://{host}/wday/cxs/{tenant}/{site}"
        budget = _positive_int(context.config.get("descriptions_per_company"), 25)
        wanted = min(context.limit, budget)

        postings: list[dict[str, Any]] = []
        offset = 0
        while len(postings) < wanted and offset < 1000:
            payload = self.get_json(
                context,
                f"{base}/jobs",
                method="POST",
                json_body={
                    "appliedFacets": {},
                    "limit": 20,
                    "offset": offset,
                    "searchText": " ".join(context.queries[:2]),
                },
            )
            batch = payload.get("jobPostings") or []
            if not batch:
                break
            postings.extend(batch)
            offset += len(batch)

        company = _company_name(tenant)
        jobs: list[RawJob] = []
        for posting in postings[:wanted]:
            if context.cancelled():
                break
            path = posting.get("externalPath") or ""
            detail = {}
            if path:
                try:
                    detail = _as_dict(self.get_json(context, f"{base}{path}").get("jobPostingInfo"))
                except SourceError:
                    # A posting pulled while we were reading is not worth failing over.
                    detail = {}
            title = detail.get("title") or posting.get("title") or ""
            if not title:
                continue
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=str(
                        detail.get("jobReqId") or _first(posting.get("bulletFields")) or path
                    ),
                    title=title,
                    company=company,
                    location=detail.get("location") or posting.get("locationsText") or "",
                    description=detail.get("jobDescription") or "",
                    url=detail.get("externalUrl") or f"https://{host}/{site}{path}",
                    # postedOn is prose like "Posted Today"; startDate is a real date.
                    posted_at=detail.get("startDate"),
                    employment=detail.get("timeType") or "",
                    raw={"board": slug, "site": site},
                )
            )
        return jobs


class Personio(_BoardAdapter):
    key = "personio"
    name = "Personio boards"
    homepage = "https://www.personio.com"
    description = "The dominant HR system in German-speaking Europe."
    address_shape = "<company>.jobs.personio.de"
    rate_limit_s = 2.0
    examples = (
        ("https://getsafe.jobs.personio.de", "getsafe"),
        ("https://mycompany.jobs.personio.com", "mycompany"),
    )

    def setup_guide(self) -> SetupGuide:
        guide = super().setup_guide()
        guide.note = (
            "Personio is the standard system for employers in Germany, Austria and "
            "Switzerland, so it reaches roles the tech-focused boards never show. The "
            "address ends in .personio.de or .personio.com; enter only the company part. "
            "Personio is the one board that publishes no description text and no posting "
            "date, so matches here are judged on the title, department and seniority "
            "alone, and these roles are never filtered out for being stale. Open the "
            "posting itself to read it in full. " + guide.note
        )
        return guide

    def fetch_company(self, slug: str, context: FetchContext) -> list[RawJob]:
        payload = self.get_json(context, f"https://{slug}.jobs.personio.de/search.json")
        if not isinstance(payload, list):
            raise SourceError("Personio returned an unexpected shape.")

        jobs: list[RawJob] = []
        for item in payload:
            title = item.get("name") or ""
            if not title:
                continue
            office = item.get("office") or ""
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=str(item.get("id", "")),
                    title=title,
                    company=item.get("subcompany") or _company_name(slug),
                    location=office,
                    # Personio's feed carries no description, so the structured
                    # fields are assembled into one instead. It is thin, but it
                    # is honest, and it gives the matcher something to read.
                    description=item.get("description") or _summary_of(item),
                    url=f"https://{slug}.jobs.personio.de/job/{item.get('id', '')}",
                    # The office line carries the arrangement, e.g. "Berlin | hybrid".
                    work_mode=_mode_from(office),
                    employment=item.get("schedule") or item.get("employment_type") or "",
                    raw={
                        "board": slug,
                        "department": item.get("department", ""),
                        "seniority": item.get("seniority", ""),
                    },
                )
            )
        return jobs


def _summary_of(item: dict[str, Any]) -> str:
    parts = [
        ("Department", item.get("department")),
        ("Category", item.get("category")),
        ("Seniority", item.get("seniority")),
        ("Employment", item.get("employment_type")),
        ("Schedule", item.get("schedule")),
        ("Office", item.get("office")),
        ("Keywords", item.get("keywords")),
    ]
    lines = [f"{label}: {value}" for label, value in parts if value]
    return "\n".join(
        ["This employer does not publish the description text. What it does publish:", *lines]
    )


def parse_workday_url(address: str) -> tuple[str, str, str]:
    """Pull ``(host, tenant, site)`` out of a Workday careers page address.

    Accepts anything from the bare host and site through to a deep link copied
    out of the middle of a search, with or without a language segment.
    """
    cleaned = address.strip().strip("<>").rstrip("/")
    if not cleaned:
        raise SourceError("A Workday address cannot be empty.")
    without_scheme = cleaned.split("://", 1)[-1]
    host, _, path = without_scheme.partition("/")
    host = host.lower()
    if "myworkdayjobs.com" not in host and "myworkdaysite.com" not in host:
        raise SourceError(
            f"'{address}' is not a Workday address. It should contain myworkdayjobs.com."
        )
    tenant = host.split(".", 1)[0]
    segments = [segment for segment in path.split("/") if segment]
    # A copied link may start with a locale, and may continue into /job/... .
    if segments and _LOCALE.fullmatch(segments[0]):
        segments = segments[1:]
    if not segments:
        raise SourceError(
            f"'{address}' has no site name. It should end with the site, for example "
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
        )
    return host, tenant, segments[0]


_LOCALE = re.compile(r"[a-z]{2}(-[A-Za-z]{2})?", re.IGNORECASE)


def _first(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    return ""


def _positive_int(value: Any, fallback: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


def _mode_from(text: str) -> str:
    lowered = text.lower()
    for mode in ("remote", "hybrid", "onsite", "on-site"):
        if mode in lowered:
            return "onsite" if mode in ("onsite", "on-site") else mode
    return ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


ADAPTERS: tuple[type[SourceAdapter], ...] = (
    Greenhouse,
    Lever,
    Ashby,
    Workable,
    Recruitee,
    SmartRecruiters,
    Workday,
    Personio,
)
