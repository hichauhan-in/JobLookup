"""Keyless public job feeds.

Every adapter here works with no signup and no API key, which is why they are
enabled by default. They are also the sources least likely to break: a public
JSON endpoint has no layout to change.
"""

from __future__ import annotations

from typing import Any

from joblookup.models import RawJob
from joblookup.sources.base import ConfigField, FetchContext, SetupGuide, SourceAdapter, SourceError


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


def _keyless_guide(
    adapter: SourceAdapter,
    *,
    summary: str,
    covers: str,
    typical: str,
    watch_out: str,
    note: str,
) -> SetupGuide:
    """The help dialog for a source with nothing to set up.

    These have no steps, so without a plain description of what they cover and
    where they fall short the dialog would say almost nothing.
    """
    return SetupGuide(
        summary=summary,
        facts=[
            ("What it covers", covers),
            ("What it needs from you", "Nothing. No account, no key, no login."),
            ("Typical run", typical),
            ("Watch out for", watch_out),
        ],
        links=[("Browse the site", adapter.homepage)] if adapter.homepage else [],
        note=note,
    )


class RemoteOK(SourceAdapter):
    key = "remoteok"
    name = "RemoteOK"
    homepage = "https://remoteok.com"
    description = "Remote-only board. One request returns the whole feed."
    rate_limit_s = 2.0

    def setup_guide(self) -> SetupGuide:
        return _keyless_guide(
            self,
            summary=(
                "RemoteOK is a long-running remote-only board, heavily weighted towards "
                "software, design and marketing. It is already on and there is nothing "
                "to configure."
            ),
            covers="Remote roles worldwide, mostly technology. Salary is often published.",
            typical="Around 100 postings per run, fetched in a single request.",
            watch_out=(
                "Many roles are remote only within the US or one timezone despite being "
                "listed as remote. Check the location line before applying."
            ),
            note=(
                "The whole board arrives in one request, so this source is fast and cheap "
                "and there is no reason to turn it off unless remote work does not "
                "interest you."
            ),
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        payload = self.get_json(context, "https://remoteok.com/api")
        if not isinstance(payload, list):
            raise SourceError("RemoteOK returned an unexpected shape.")

        jobs: list[RawJob] = []
        # The first element is a legal notice, not a job.
        for item in payload[1:]:
            if not isinstance(item, dict):
                continue
            title = item.get("position") or item.get("title") or ""
            if not title:
                continue
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=str(item.get("id", "")),
                    title=title,
                    company=item.get("company") or "",
                    location=item.get("location") or "Remote",
                    description=item.get("description") or "",
                    url=item.get("url") or f"https://remoteok.com/l/{item.get('id', '')}",
                    apply_url=item.get("apply_url") or "",
                    posted_at=item.get("date") or item.get("epoch"),
                    work_mode="remote",
                    salary_min=_float(item.get("salary_min")),
                    salary_max=_float(item.get("salary_max")),
                    salary_currency="USD" if item.get("salary_min") else "",
                    raw={"tags": item.get("tags") or []},
                )
            )
            if len(jobs) >= context.limit:
                break
        return jobs


class Remotive(SourceAdapter):
    key = "remotive"
    name = "Remotive"
    homepage = "https://remotive.com"
    description = "Curated remote roles, mostly tech and product."

    def setup_guide(self) -> SetupGuide:
        return _keyless_guide(
            self,
            summary=(
                "Remotive is a curated remote board: a person reviews what gets listed, "
                "so the volume is low but the quality is high."
            ),
            covers="Remote technology, product and customer roles, worldwide.",
            typical="Usually 20 to 100 postings per run. Curation keeps the number small.",
            watch_out=(
                "Low volume is normal here and is not a sign of a broken source. Many "
                "listings restrict which countries they will hire from."
            ),
            note="Nothing to set up. It is on by default and costs one request per run.",
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        params: dict[str, Any] = {"limit": min(context.limit, 200)}
        if context.queries:
            params["search"] = context.queries[0]
        payload = self.get_json(context, "https://remotive.com/api/remote-jobs", params=params)

        jobs: list[RawJob] = []
        for item in payload.get("jobs") or []:
            title = item.get("title") or ""
            if not title:
                continue
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=str(item.get("id", "")),
                    title=title,
                    company=item.get("company_name") or "",
                    location=item.get("candidate_required_location") or "Remote",
                    description=item.get("description") or "",
                    url=item.get("url") or "",
                    posted_at=item.get("publication_date"),
                    work_mode="remote",
                    employment=(item.get("job_type") or "").replace("_", "-"),
                    raw={"category": item.get("category", "")},
                )
            )
            if len(jobs) >= context.limit:
                break
        return jobs


class Arbeitnow(SourceAdapter):
    key = "arbeitnow"
    name = "Arbeitnow (Europe)"
    homepage = "https://www.arbeitnow.com"
    description = "European postings, strong in Germany and the Netherlands."

    def setup_guide(self) -> SetupGuide:
        return _keyless_guide(
            self,
            summary=(
                "Arbeitnow is a European board built around German-speaking Europe. It is "
                "unusually good at flagging roles that will sponsor a visa, which makes it "
                "the most useful keyless source if you are moving to Europe."
            ),
            covers="Europe, especially Germany and the Netherlands. Office and remote both.",
            typical="Around 200 postings per run, fetched over several pages.",
            watch_out=(
                "Many descriptions are in German. The matcher reads them fine, but you "
                "will want the browser's translate function when you open one."
            ),
            note="Nothing to set up. Worth leaving on even outside Europe for remote roles.",
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        jobs: list[RawJob] = []
        for page in range(1, 6):
            if context.cancelled():
                break
            payload = self.get_json(
                context, "https://www.arbeitnow.com/api/job-board-api", params={"page": page}
            )
            items = payload.get("data") or []
            if not items:
                break
            for item in items:
                title = item.get("title") or ""
                if not title:
                    continue
                jobs.append(
                    RawJob(
                        source_key=self.key,
                        source_job_id=str(item.get("slug", "")),
                        title=title,
                        company=item.get("company_name") or "",
                        location=item.get("location") or "",
                        description=item.get("description") or "",
                        url=item.get("url") or "",
                        posted_at=item.get("created_at"),
                        work_mode="remote" if item.get("remote") else "",
                        employment=", ".join(item.get("job_types") or []),
                        raw={"tags": item.get("tags") or []},
                    )
                )
                if len(jobs) >= context.limit:
                    return jobs
        return jobs


class Himalayas(SourceAdapter):
    key = "himalayas"
    name = "Himalayas"
    homepage = "https://himalayas.app"
    description = "Remote roles with explicit country restrictions and salary bands."

    def setup_guide(self) -> SetupGuide:
        return _keyless_guide(
            self,
            summary=(
                "Himalayas lists remote-first companies and publishes the cleanest "
                "structured data of any keyless source: salary ranges, seniority and the "
                "countries a role can be done from are all proper fields rather than prose."
            ),
            covers="Remote roles worldwide from companies that are remote by default.",
            typical="Around 160 postings per run.",
            watch_out=(
                "Skews towards startups and scale-ups, so large-employer roles are rare "
                "here. Pair it with the company boards."
            ),
            note=(
                "Because the country restrictions are a real field rather than prose, this "
                "is the keyless source least likely to show you a role you cannot take."
            ),
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        jobs: list[RawJob] = []
        offset = 0
        page_size = 50
        while len(jobs) < context.limit and offset < 400:
            if context.cancelled():
                break
            payload = self.get_json(
                context,
                "https://himalayas.app/jobs/api",
                params={"limit": page_size, "offset": offset},
            )
            items = payload.get("jobs") or []
            if not items:
                break
            for item in items:
                title = item.get("title") or ""
                if not title:
                    continue
                restrictions = item.get("locationRestrictions") or []
                jobs.append(
                    RawJob(
                        source_key=self.key,
                        source_job_id=str(item.get("guid", "")),
                        title=title,
                        company=item.get("companyName") or "",
                        location=", ".join(restrictions) if restrictions else "Remote",
                        description=item.get("description") or "",
                        url=item.get("applicationLink") or item.get("guid") or "",
                        posted_at=item.get("pubDate"),
                        work_mode="remote",
                        salary_min=_float(item.get("minSalary")),
                        salary_max=_float(item.get("maxSalary")),
                        salary_currency=item.get("salaryCurrency") or "",
                        raw={"seniority": item.get("seniority") or []},
                    )
                )
                if len(jobs) >= context.limit:
                    break
            offset += page_size
        return jobs


class TheMuse(SourceAdapter):
    key = "themuse"
    name = "The Muse"
    homepage = "https://www.themuse.com"
    description = "Mid-to-large employers, mostly US, with clean company profiles."
    rate_limit_s = 1.5

    def setup_guide(self) -> SetupGuide:
        return _keyless_guide(
            self,
            summary=(
                "The Muse is the only keyless source here that is general-purpose rather "
                "than remote-only, which makes it the one that matters most if you are "
                "looking for ordinary office-based work."
            ),
            covers="Mid-to-large employers across every sector. Heavily US-weighted.",
            typical="Around 100 postings per run, fetched over several pages.",
            watch_out=(
                "Coverage outside the United States is thin. If you are elsewhere, the "
                "country pack at the top of this screen will point you at better options."
            ),
            note=(
                "It uses the places from your profile to narrow the search, so filling in "
                "your locations on the Profile screen improves what this source returns."
            ),
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        jobs: list[RawJob] = []
        for page in range(0, 5):
            if context.cancelled() or len(jobs) >= context.limit:
                break
            params: dict[str, Any] = {"page": page, "descending": "true"}
            if context.locations:
                params["location"] = context.locations[:3]
            payload = self.get_json(
                context, "https://www.themuse.com/api/public/jobs", params=params
            )
            items = payload.get("results") or []
            if not items:
                break
            for item in items:
                title = item.get("name") or ""
                if not title:
                    continue
                locations = [entry.get("name", "") for entry in item.get("locations") or []]
                landing = (item.get("refs") or {}).get("landing_page", "")
                jobs.append(
                    RawJob(
                        source_key=self.key,
                        source_job_id=str(item.get("id", "")),
                        title=title,
                        company=(item.get("company") or {}).get("name", ""),
                        location=", ".join(locations),
                        description=item.get("contents") or "",
                        url=landing,
                        posted_at=item.get("publication_date"),
                        raw={"levels": [lvl.get("name") for lvl in item.get("levels") or []]},
                    )
                )
                if len(jobs) >= context.limit:
                    break
        return jobs


class Jobicy(SourceAdapter):
    key = "jobicy"
    name = "Jobicy"
    homepage = "https://jobicy.com"
    description = "Remote-only board with full descriptions and a geography tag per role."
    rate_limit_s = 1.5

    def config_fields(self) -> list[ConfigField]:
        return [
            ConfigField(
                "geo",
                "Limit to a region",
                "text",
                placeholder="usa",
                help=(
                    "Remote does not mean worldwide, and Jobicy can narrow the feed to "
                    "roles open to one place. Try usa, uk, germany, canada, australia, "
                    "singapore or apac. Leave empty for everything."
                ),
            )
        ]

    def setup_guide(self) -> SetupGuide:
        guide = _keyless_guide(
            self,
            summary=(
                "Jobicy is a remote board that publishes full descriptions and, unusually, "
                "tags every role with the places it can be done from. That tag is why it "
                "can be narrowed to one region, which the country packs do for you."
            ),
            covers="Remote roles worldwide, across technology, marketing, support and design.",
            typical="Up to 50 postings per run, with the complete description text.",
            watch_out=(
                "The region filter is Jobicy's own list, not a country code. An unknown "
                "value is ignored rather than failing the source."
            ),
            note=(
                "Leave the region empty to get everything. The country packs set it for "
                "you, so you rarely need to touch it by hand."
            ),
        )
        guide.examples = [
            ("Looking in the United States, enter", "usa"),
            ("Looking in the UK, enter", "uk"),
            ("Looking in India or wider Asia, enter", "apac"),
            ("Looking anywhere at all, leave it", "empty"),
        ]
        return guide

    def fetch(self, context: FetchContext) -> list[RawJob]:
        params: dict[str, Any] = {"count": min(context.limit, 50)}
        geo = str(context.config.get("geo") or "").strip().lower()
        if geo:
            params["geo"] = geo
        try:
            payload = self.get_json(context, "https://jobicy.com/api/v2/remote-jobs", params=params)
        except SourceError:
            if not geo:
                raise
            # An unsupported region is a 400, which should cost you the filter
            # rather than the whole source.
            context.log(f"Jobicy does not know the region '{geo}'; fetching everything instead.")
            payload = self.get_json(
                context, "https://jobicy.com/api/v2/remote-jobs", params={"count": params["count"]}
            )
        jobs: list[RawJob] = []
        for item in payload.get("jobs") or []:
            title = item.get("jobTitle") or ""
            if not title:
                continue
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=str(item.get("id", "")),
                    title=title,
                    company=item.get("companyName") or "",
                    location=item.get("jobGeo") or "Anywhere",
                    description=item.get("jobDescription") or item.get("jobExcerpt") or "",
                    url=item.get("url") or "",
                    posted_at=item.get("pubDate"),
                    work_mode="remote",
                    employment=", ".join(item.get("jobType") or []),
                    salary_min=_float(item.get("annualSalaryMin")),
                    salary_max=_float(item.get("annualSalaryMax")),
                    salary_currency=item.get("salaryCurrency") or "",
                    raw={
                        "industry": item.get("jobIndustry") or [],
                        "level": item.get("jobLevel") or "",
                    },
                )
            )
            if len(jobs) >= context.limit:
                break
        return jobs


class WorkingNomads(SourceAdapter):
    key = "workingnomads"
    name = "Working Nomads"
    homepage = "https://www.workingnomads.com"
    description = "Hand-curated remote roles across development, marketing and operations."
    rate_limit_s = 2.0

    def setup_guide(self) -> SetupGuide:
        return _keyless_guide(
            self,
            summary=(
                "Working Nomads is hand-curated and reaches further beyond engineering "
                "than most remote boards, so it is worth having alongside the others "
                "rather than instead of them."
            ),
            covers="Remote roles in development, marketing, management, design and support.",
            typical="Around 50 postings per run, fetched in a single request.",
            watch_out=(
                "The location field lists broad regions such as 'Europe, North America' "
                "rather than countries, so read it before assuming a role is open to you."
            ),
            note="Nothing to set up. One request per run, so it costs almost nothing.",
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        payload = self.get_json(context, "https://www.workingnomads.com/api/exposed_jobs/")
        if not isinstance(payload, list):
            raise SourceError("Working Nomads returned an unexpected shape.")

        jobs: list[RawJob] = []
        for item in payload:
            title = item.get("title") or ""
            if not title:
                continue
            url = item.get("url") or ""
            jobs.append(
                RawJob(
                    source_key=self.key,
                    # The listing has no id of its own, but the URL carries one.
                    source_job_id=url.rstrip("/").rsplit("/", 1)[-1],
                    title=title,
                    company=item.get("company_name") or "",
                    location=item.get("location") or "Anywhere",
                    description=item.get("description") or "",
                    url=url,
                    posted_at=item.get("pub_date"),
                    work_mode="remote",
                    raw={
                        "category": item.get("category_name") or "",
                        "tags": (item.get("tags") or "").split(","),
                    },
                )
            )
            if len(jobs) >= context.limit:
                break
        return jobs


class WeWorkRemotely(SourceAdapter):
    key = "weworkremotely"
    name = "We Work Remotely"
    homepage = "https://weworkremotely.com"
    description = "One of the largest remote boards. Published as an RSS feed."
    rate_limit_s = 2.0

    def setup_guide(self) -> SetupGuide:
        return _keyless_guide(
            self,
            summary=(
                "We Work Remotely is one of the largest remote boards anywhere. It has no "
                "JSON API, so JobLookup reads its public RSS feed instead."
            ),
            covers="Remote roles worldwide: engineering, design, marketing, support and more.",
            typical="100 postings per run, which is the full length of the feed.",
            watch_out=(
                "The feed carries the newest 100 roles only, so run searches regularly "
                "rather than rarely if this source matters to you."
            ),
            note=(
                "Company and role arrive joined together in one line and are split apart "
                "here. If a company name ever looks wrong on a posting from this source, "
                "that split is why."
            ),
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        root = self.get_xml(context, "https://weworkremotely.com/remote-jobs.rss")
        jobs: list[RawJob] = []
        for item in root.findall(".//item"):
            raw_title = _text(item, "title")
            if not raw_title:
                continue
            # Titles arrive as "Company: Role", which is the only company field there is.
            company, _, title = raw_title.partition(": ")
            if not title:
                company, title = "", raw_title
            region = _text(item, "region") or _text(item, "country")
            jobs.append(
                RawJob(
                    source_key=self.key,
                    source_job_id=_text(item, "guid") or _text(item, "link"),
                    title=title,
                    company=company,
                    location=region or "Anywhere",
                    description=_text(item, "description"),
                    url=_text(item, "link"),
                    posted_at=_text(item, "pubDate"),
                    work_mode="remote",
                    employment=_text(item, "type"),
                    raw={
                        "category": _text(item, "category"),
                        "skills": _text(item, "skills"),
                    },
                )
            )
            if len(jobs) >= context.limit:
                break
        return jobs


def _text(item: Any, tag: str) -> str:
    node = item.find(tag)
    return (node.text or "").strip() if node is not None else ""


ADAPTERS: tuple[type[SourceAdapter], ...] = (
    RemoteOK,
    Remotive,
    Arbeitnow,
    Himalayas,
    TheMuse,
    Jobicy,
    WorkingNomads,
    WeWorkRemotely,
)
