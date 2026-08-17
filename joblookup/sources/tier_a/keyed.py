"""Public APIs that need a free account.

Each of these has a free tier that is generous enough for one person's job
search. The key is stored in Windows Credential Manager where that is available
and in an owner-only file otherwise — never in a config file, and never sent
anywhere except the API it belongs to.
"""

from __future__ import annotations

import base64
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


class Adzuna(SourceAdapter):
    key = "adzuna"
    name = "Adzuna"
    homepage = "https://developer.adzuna.com"
    description = "Aggregator with good coverage in the UK, EU, US, India and Australia."
    requires_key = True
    rate_limit_s = 1.0

    def config_fields(self) -> list[ConfigField]:
        return [
            ConfigField(
                "app_id",
                "Application ID",
                "password",
                required=True,
                help="From developer.adzuna.com. Free, and issued instantly.",
            ),
            ConfigField("app_key", "Application key", "password", required=True),
            ConfigField(
                "countries",
                "Country codes",
                "list",
                placeholder="gb, us, in",
                help="Adzuna searches one country per request. Two-letter codes.",
            ),
        ]

    def is_configured(self, context: FetchContext) -> tuple[bool, str]:
        if not (context.secret("adzuna_app_id") and context.secret("adzuna_app_key")):
            return False, "Add the Adzuna application ID and key."
        return True, ""

    def setup_guide(self) -> SetupGuide:
        return SetupGuide(
            summary=(
                "Adzuna is a free job aggregator with good coverage in the UK, EU, US, "
                "India and Australia. The key is free, personal, and issued the moment "
                "you sign up."
            ),
            steps=[
                "Open developer.adzuna.com and press Sign up.",
                "Fill in the short form. There is no approval wait and no card.",
                "You land on a dashboard showing an Application ID and an Application Key.",
                "Copy both into the API keys panel below and press Store keys.",
                "Set the country codes you care about, e.g. gb, us, in.",
            ],
            links=[("Get an Adzuna key", "https://developer.adzuna.com/signup")],
            examples=[
                ("Application ID looks like", "a1b2c3d4"),
                ("Application Key looks like", "9f8e7d6c5b4a39281706..."),
                ("Country codes", "gb, us, in"),
            ],
            note=(
                "The free tier allows a few hundred calls a day, which is far more than "
                "one person's job search uses. Your keys go into Windows Credential "
                "Manager, never into a config file."
            ),
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        app_id = context.secret("adzuna_app_id")
        app_key = context.secret("adzuna_app_key")
        if not (app_id and app_key):
            raise SourceError("Adzuna credentials are missing.")

        countries = as_list(context.config.get("countries")) or ["gb"]
        queries = context.queries[:3] or [""]
        jobs: list[RawJob] = []

        for country in countries[:4]:
            for query in queries:
                if context.cancelled() or len(jobs) >= context.limit:
                    return jobs[: context.limit]
                params: dict[str, Any] = {
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": 50,
                    "max_days_old": context.recency_days,
                    "content-type": "application/json",
                }
                if query:
                    params["what"] = query
                if context.locations:
                    params["where"] = context.locations[0]
                payload = self.get_json(
                    context,
                    f"https://api.adzuna.com/v1/api/jobs/{country.lower()}/search/1",
                    params=params,
                )
                for item in payload.get("results") or []:
                    location = ", ".join((item.get("location") or {}).get("area") or [])
                    jobs.append(
                        RawJob(
                            source_key=self.key,
                            source_job_id=str(item.get("id", "")),
                            title=item.get("title") or "",
                            company=(item.get("company") or {}).get("display_name", ""),
                            location=location,
                            description=item.get("description") or "",
                            url=item.get("redirect_url") or "",
                            posted_at=item.get("created"),
                            employment=item.get("contract_time") or "",
                            salary_min=item.get("salary_min"),
                            salary_max=item.get("salary_max"),
                            salary_currency=_currency_for(country),
                            raw={
                                "country": country,
                                "category": (item.get("category") or {}).get("label", ""),
                            },
                        )
                    )
        return jobs[: context.limit]


def _currency_for(country: str) -> str:
    return {
        "gb": "GBP",
        "us": "USD",
        "in": "INR",
        "au": "AUD",
        "ca": "CAD",
        "de": "EUR",
        "fr": "EUR",
        "nl": "EUR",
        "at": "EUR",
        "it": "EUR",
        "es": "EUR",
        "pl": "PLN",
        "sg": "SGD",
        "za": "ZAR",
        "nz": "NZD",
        "br": "BRL",
        "mx": "MXN",
        "ru": "RUB",
    }.get(country.lower(), "")


class Jooble(SourceAdapter):
    key = "jooble"
    name = "Jooble"
    homepage = "https://jooble.org/api/about"
    description = "Worldwide aggregator. One key, no country restriction."
    requires_key = True

    def config_fields(self) -> list[ConfigField]:
        return [ConfigField("api_key", "API key", "password", required=True)]

    def is_configured(self, context: FetchContext) -> tuple[bool, str]:
        return (True, "") if context.secret("jooble") else (False, "Add the Jooble API key.")

    def setup_guide(self) -> SetupGuide:
        return SetupGuide(
            summary=(
                "Jooble aggregates postings worldwide. One key covers every country, so "
                "there is nothing else to configure."
            ),
            steps=[
                "Open jooble.org/api/about.",
                "Fill in the request form with your name and email.",
                "The key is shown on the page, and also emailed to you.",
                "Paste it into the API keys panel below and press Store keys.",
            ],
            links=[("Request a Jooble key", "https://jooble.org/api/about")],
            examples=[("The key looks like", "1a2b3c4d-5e6f-7890-abcd-ef1234567890")],
            note="Free for personal use. The key is the only thing Jooble needs from you.",
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        api_key = context.secret("jooble")
        if not api_key:
            raise SourceError("Jooble API key is missing.")

        jobs: list[RawJob] = []
        for query in context.queries[:3] or [""]:
            if context.cancelled() or len(jobs) >= context.limit:
                break
            payload = self.get_json(
                context,
                f"https://jooble.org/api/{api_key}",
                method="POST",
                json_body={
                    "keywords": query,
                    "location": context.locations[0] if context.locations else "",
                    "page": "1",
                },
                headers={"content-type": "application/json"},
            )
            for item in payload.get("jobs") or []:
                jobs.append(
                    RawJob(
                        source_key=self.key,
                        source_job_id=str(item.get("id", "")),
                        title=item.get("title") or "",
                        company=item.get("company") or "",
                        location=item.get("location") or "",
                        description=item.get("snippet") or "",
                        url=item.get("link") or "",
                        posted_at=item.get("updated"),
                        employment=item.get("type") or "",
                        raw={"salary": item.get("salary", "")},
                    )
                )
                if len(jobs) >= context.limit:
                    break
        return jobs


class USAJobs(SourceAdapter):
    key = "usajobs"
    name = "USAJOBS (US federal)"
    homepage = "https://developer.usajobs.gov"
    description = "Every US federal government opening. Free key, issued by email."
    requires_key = True

    def config_fields(self) -> list[ConfigField]:
        return [
            ConfigField(
                "email",
                "Registered email",
                "text",
                required=True,
                help="USAJOBS sends the key here and expects it as the user agent.",
            ),
            ConfigField("api_key", "Authorisation key", "password", required=True),
        ]

    def is_configured(self, context: FetchContext) -> tuple[bool, str]:
        if not (context.secret("usajobs") and context.secret("usajobs_email")):
            return False, "Add the USAJOBS email and authorisation key."
        return True, ""

    def setup_guide(self) -> SetupGuide:
        return SetupGuide(
            summary=(
                "USAJOBS carries every US federal government opening. Only useful if you "
                "can work in the United States, and many roles additionally require "
                "citizenship."
            ),
            steps=[
                "Open developer.usajobs.gov/apirequest/ and complete the request form.",
                "The authorisation key arrives by email, usually within a few minutes.",
                "Enter the same email address you registered with, plus the key, below.",
            ],
            links=[("Request a USAJOBS key", "https://developer.usajobs.gov/apirequest/")],
            examples=[
                ("Registered email", "you@example.com"),
                ("Authorisation key looks like", "aBcDeF1234567890aBcDeF=="),
            ],
            note=(
                "USAJOBS requires the email you registered with to be sent as the user "
                "agent on every request, which is why it asks for both. That is their "
                "documented requirement, not something JobLookup invented."
            ),
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        api_key = context.secret("usajobs")
        email = context.secret("usajobs_email")
        if not (api_key and email):
            raise SourceError("USAJOBS credentials are missing.")

        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": email,
            "Authorization-Key": api_key,
        }
        jobs: list[RawJob] = []
        for query in context.queries[:3] or [""]:
            if context.cancelled() or len(jobs) >= context.limit:
                break
            params: dict[str, Any] = {
                "ResultsPerPage": 50,
                "SortField": "OpenDate",
                "SortDirection": "Desc",
            }
            if query:
                params["Keyword"] = query
            if context.locations:
                params["LocationName"] = context.locations[0]
            payload = self.get_json(
                context, "https://data.usajobs.gov/api/search", params=params, headers=headers
            )
            items = ((payload.get("SearchResult") or {}).get("SearchResultItems")) or []
            for entry in items:
                item = entry.get("MatchedObjectDescriptor") or {}
                details = item.get("UserArea", {}).get("Details", {}) or {}
                remuneration = (item.get("PositionRemuneration") or [{}])[0]
                jobs.append(
                    RawJob(
                        source_key=self.key,
                        source_job_id=str(entry.get("MatchedObjectId", "")),
                        title=item.get("PositionTitle") or "",
                        company=item.get("OrganizationName") or "",
                        location=", ".join(
                            loc.get("LocationName", "")
                            for loc in item.get("PositionLocation") or []
                        )[:200],
                        description="\n\n".join(
                            part
                            for part in (
                                item.get("QualificationSummary") or "",
                                details.get("JobSummary") or "",
                                details.get("MajorDuties")
                                and " ".join(details["MajorDuties"])
                                or "",
                            )
                            if part
                        ),
                        url=item.get("PositionURI") or "",
                        apply_url=(item.get("ApplyURI") or [""])[0],
                        posted_at=item.get("PublicationStartDate"),
                        employment=", ".join(
                            schedule.get("Name", "")
                            for schedule in item.get("PositionSchedule") or []
                        ),
                        salary_min=_as_float(remuneration.get("MinimumRange")),
                        salary_max=_as_float(remuneration.get("MaximumRange")),
                        salary_currency="USD",
                        raw={"grade": details.get("LowGrade", "")},
                    )
                )
                if len(jobs) >= context.limit:
                    break
        return jobs


class Findwork(SourceAdapter):
    key = "findwork"
    name = "Findwork"
    homepage = "https://findwork.dev/developers"
    description = "Developer-focused board with a free API tier."
    requires_key = True

    def config_fields(self) -> list[ConfigField]:
        return [ConfigField("api_key", "API token", "password", required=True)]

    def is_configured(self, context: FetchContext) -> tuple[bool, str]:
        return (True, "") if context.secret("findwork") else (False, "Add the Findwork API token.")

    def setup_guide(self) -> SetupGuide:
        return SetupGuide(
            summary="Findwork is a smaller, developer-focused board with a free API tier.",
            steps=[
                "Open findwork.dev and create an account.",
                "Go to findwork.dev/developers and copy the API token shown there.",
                "Paste it into the API keys panel below and press Store keys.",
            ],
            links=[("Get a Findwork token", "https://findwork.dev/developers/")],
            examples=[("The token looks like", "0a1b2c3d4e5f60718293a4b5c6d7e8f900112233")],
            note="The free tier is rate limited but ample for one person searching.",
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        token = context.secret("findwork")
        if not token:
            raise SourceError("Findwork API token is missing.")

        headers = {"Authorization": f"Token {token}"}
        jobs: list[RawJob] = []
        for query in context.queries[:3] or [""]:
            if context.cancelled() or len(jobs) >= context.limit:
                break
            params: dict[str, Any] = {"sort_by": "date"}
            if query:
                params["search"] = query
            if context.locations:
                params["location"] = context.locations[0]
            payload = self.get_json(
                context, "https://findwork.dev/api/jobs/", params=params, headers=headers
            )
            for item in payload.get("results") or []:
                jobs.append(
                    RawJob(
                        source_key=self.key,
                        source_job_id=str(item.get("id", "")),
                        title=item.get("role") or "",
                        company=item.get("company_name") or "",
                        location=item.get("location") or ("Remote" if item.get("remote") else ""),
                        description=item.get("text") or "",
                        url=item.get("url") or "",
                        posted_at=item.get("date_posted"),
                        employment=item.get("employment_type") or "",
                        work_mode="remote" if item.get("remote") else "",
                        raw={"keywords": item.get("keywords") or []},
                    )
                )
                if len(jobs) >= context.limit:
                    break
        return jobs


class Reed(SourceAdapter):
    key = "reed"
    name = "Reed (UK)"
    homepage = "https://www.reed.co.uk/developers"
    description = "The largest UK job board, covering every sector rather than just tech."
    requires_key = True
    rate_limit_s = 1.0

    def config_fields(self) -> list[ConfigField]:
        return [
            ConfigField(
                "locations",
                "Places to search",
                "list",
                placeholder="London, Manchester",
                help="Leave empty to search the whole UK. Separate several with commas.",
            ),
            ConfigField(
                "distance_miles",
                "Distance from each place",
                "number",
                placeholder="15",
                help="How far from each town to look. Ignored when no place is set.",
            ),
        ]

    def is_configured(self, context: FetchContext) -> tuple[bool, str]:
        if not context.secret("reed"):
            return False, "Add the Reed API key."
        return True, ""

    def setup_guide(self) -> SetupGuide:
        return SetupGuide(
            summary=(
                "Reed is the biggest job board in the UK and covers every sector, not "
                "just technology. If you are looking in Britain this is the single most "
                "useful key to get. It is free and issued by email."
            ),
            steps=[
                "Open reed.co.uk/developers and press Register for free.",
                "Sign in or create an ordinary Reed account.",
                "Confirm the short form. Your API key appears on the developers page.",
                "Copy it into the API keys panel below and press Store keys.",
                "Optionally set the towns you want searched and how far around them.",
            ],
            links=[("Get a Reed key", "https://www.reed.co.uk/developers/jobseeker")],
            examples=[
                ("The key looks like", "a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
                ("Places to search", "London, Manchester"),
                ("Distance from each place", "15"),
            ],
            note=(
                "Reed authenticates with the key as the username and no password, which "
                "this app does for you. The key is stored in Windows Credential Manager, "
                "never in a config file."
            ),
        )

    def fetch(self, context: FetchContext) -> list[RawJob]:
        key = context.secret("reed")
        if not key:
            raise SourceError("The Reed API key is missing.")

        places = as_list(context.config.get("locations")) or context.locations[:2] or [""]
        queries = context.queries[:3] or [""]
        distance = context.config.get("distance_miles")
        jobs: list[RawJob] = []

        for place in places[:3]:
            for query in queries:
                if context.cancelled() or len(jobs) >= context.limit:
                    return jobs[: context.limit]
                params: dict[str, Any] = {"resultsToTake": 100}
                if query:
                    params["keywords"] = query
                if place:
                    params["locationName"] = place
                    if distance:
                        params["distanceFromLocation"] = distance
                payload = self.get_json(
                    context,
                    "https://www.reed.co.uk/api/1.0/search",
                    params=params,
                    # The key is the username and the password is empty.
                    headers={"authorization": _basic(key)},
                )
                for item in payload.get("results") or []:
                    jobs.append(
                        RawJob(
                            source_key=self.key,
                            source_job_id=str(item.get("jobId", "")),
                            title=item.get("jobTitle") or "",
                            company=item.get("employerName") or "",
                            location=item.get("locationName") or "",
                            description=item.get("jobDescription") or "",
                            url=item.get("jobUrl") or "",
                            posted_at=item.get("date"),
                            salary_min=_as_float(item.get("minimumSalary")),
                            salary_max=_as_float(item.get("maximumSalary")),
                            salary_currency=item.get("currency") or "GBP",
                            raw={"expires": item.get("expirationDate", "")},
                        )
                    )
        return jobs[: context.limit]


def _basic(key: str) -> str:
    token = base64.b64encode(f"{key}:".encode()).decode("ascii")
    return f"Basic {token}"


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


ADAPTERS: tuple[type[SourceAdapter], ...] = (Adzuna, Jooble, USAJobs, Findwork, Reed)
