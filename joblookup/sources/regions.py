"""Country packs: the same sources, ordered by what actually works where you are.

The other three sections on the Sources screen are organised by how a source
works. This one is organised by where you are looking, because that is the
question a person actually has. Nothing here is a new source — a pack is a
curated shortlist of the sources already in the app, in the order they are worth
your time in that country, with the country-specific settings filled in.

Picking a pack never turns on anything risky. Keyless sources are switched on,
country settings are filled in, and anything needing a key, a company list or a
login is listed with what it needs so you can decide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_REGION = "in"


@dataclass(frozen=True, slots=True)
class Pick:
    """One source worth using in this region, and the reason why."""

    key: str
    why: str
    #: Country settings written to the source when the pack is applied.
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "why": self.why, "config": dict(self.config)}


@dataclass(frozen=True, slots=True)
class Region:
    code: str
    name: str
    summary: str
    picks: tuple[Pick, ...]
    note: str = ""
    #: Remote packs filter results to remote roles rather than to a place.
    remote_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "summary": self.summary,
            "note": self.note,
            "remote_only": self.remote_only,
            "picks": [pick.to_dict() for pick in self.picks],
        }


# Shared reasons, so the same source reads consistently across packs.
_GLOBAL_BOARDS = "Global employers hire here through their own board, which is always freshest."
_LINKEDIN = "The widest coverage anywhere, but it needs a login and carries the usual risk."

REGIONS: tuple[Region, ...] = (
    Region(
        code="in",
        name="India",
        summary=(
            "Indian hiring runs through Naukri and LinkedIn far more than through open "
            "APIs, so the honest picture is two keyless remote boards to start you off, "
            "Adzuna and Jooble once you have their free keys, the global company boards "
            "for multinationals hiring in India, and the local portals if you accept what "
            "a login costs."
        ),
        picks=(
            Pick(
                "jobicy",
                "Remote roles, filtered to the ones open across Asia-Pacific.",
                {"geo": "apac"},
            ),
            Pick("remoteok", "Worldwide remote roles, many of them open to India. No key."),
            Pick(
                "adzuna",
                "Good Indian coverage and the key is free and instant.",
                {"countries": ["in"]},
            ),
            Pick(
                "jooble",
                "Aggregates the Indian boards, including some Naukri listings.",
            ),
            Pick("greenhouse", _GLOBAL_BOARDS),
            Pick("lever", _GLOBAL_BOARDS),
            Pick("ashby", "Well-funded startups with India engineering teams."),
            Pick("workday", "Nearly every large multinational with an India office uses it."),
            Pick("naukri", "The dominant Indian job board. Nothing else comes close locally."),
            Pick("instahyre", "Curated Indian tech roles, strong for experienced engineers."),
            Pick("cutshort", "Indian startup hiring, good signal-to-noise."),
            Pick("foundit", "Formerly Monster India. Broad, beyond technology."),
            Pick("linkedin", _LINKEDIN),
        ),
        note=(
            "India has no free, keyless, general job API, which is why this pack opens "
            "with two remote boards: they are the only things that work the moment you "
            "press the button. Adzuna and Jooble are the best general coverage available "
            "and both keys are free. The four Indian portals need a login and are against "
            "those sites' terms of service, so they stay off until you turn them on."
        ),
    ),
    Region(
        code="remote",
        name="Remote (anywhere)",
        summary=(
            "Ignore geography and search remote-first boards instead. This is the one pack "
            "that also filters what comes back, so office-based roles are dropped even when "
            "a source sends them."
        ),
        picks=(
            Pick("remoteok", "One request returns the whole board."),
            Pick("weworkremotely", "One of the largest remote boards anywhere."),
            Pick("remotive", "Curated remote roles, mostly technology and product."),
            Pick("jobicy", "Full descriptions and a clear geography tag per role."),
            Pick("workingnomads", "Hand-curated, and reaches beyond engineering."),
            Pick("himalayas", "Remote-first companies with good structured data."),
            Pick("arbeitnow", "European remote roles, many of them visa-friendly."),
            Pick("wellfound", "Startup remote roles. Needs a login."),
            Pick("ashby", "Remote-first startups publish here first."),
            Pick("greenhouse", "Set a company you want and catch its remote roles early."),
        ),
        note=(
            "Remote does not mean worldwide. Many roles on these boards are remote within "
            "one country or timezone, so check the location line before applying. While "
            "this pack is selected, any posting not positively identified as remote is "
            "filtered out, including ones that simply never say either way."
        ),
        remote_only=True,
    ),
    Region(
        code="us",
        name="United States",
        summary=(
            "The best-served country in the app: a free federal API, strong aggregator "
            "coverage, and almost every company board worth watching is American."
        ),
        picks=(
            Pick("themuse", "Mid-to-large US employers, no key needed."),
            Pick("jobicy", "Remote roles open to US candidates. No key.", {"geo": "usa"}),
            Pick("usajobs", "Every US federal government job. Free key, and unique coverage."),
            Pick("adzuna", "Broad US aggregation.", {"countries": ["us"]}),
            Pick("greenhouse", _GLOBAL_BOARDS),
            Pick("lever", _GLOBAL_BOARDS),
            Pick("ashby", "Well-funded US startups."),
            Pick("workday", "Most large US employers run their careers site on it."),
            Pick("smartrecruiters", "Large US enterprises outside technology."),
            Pick("findwork", "US-centric technology roles. Free key."),
            Pick("dice", "US technology and contract roles. Needs a login."),
            Pick("indeed", "The largest US aggregator. Needs a login."),
            Pick("linkedin", _LINKEDIN),
        ),
    ),
    Region(
        code="gb",
        name="United Kingdom",
        summary=(
            "Reed is the single most useful thing you can add here: it is the largest UK "
            "board and it covers every sector rather than just technology."
        ),
        picks=(
            Pick("jobicy", "Remote roles open to UK candidates. Works with no key.", {"geo": "uk"}),
            Pick("reed", "The largest UK board, all sectors. Free key."),
            Pick(
                "adzuna",
                "Adzuna began in the UK and coverage is strongest here.",
                {"countries": ["gb"]},
            ),
            Pick("jooble", "Fills gaps around the two above."),
            Pick("greenhouse", _GLOBAL_BOARDS),
            Pick("lever", _GLOBAL_BOARDS),
            Pick("workday", "Large UK employers and the UK arms of multinationals."),
            Pick("workable", "Widely used by UK small and mid-size employers."),
            Pick("indeed", "Broad UK coverage. Needs a login."),
            Pick("linkedin", _LINKEDIN),
        ),
    ),
    Region(
        code="de",
        name="Germany, Austria and Switzerland",
        summary=(
            "German-speaking Europe runs on Personio far more than on the boards the "
            "English-language job sites index, so Personio is the pack's centrepiece."
        ),
        picks=(
            Pick(
                "personio",
                "The dominant HR system in the region. Reaches roles nothing else does.",
            ),
            Pick("arbeitnow", "German and EU roles, no key, many marked visa-friendly."),
            Pick("jobicy", "Remote roles open to German candidates.", {"geo": "germany"}),
            Pick("adzuna", "Solid German coverage.", {"countries": ["de"]}),
            Pick("jooble", "Adds Austrian and Swiss listings."),
            Pick("recruitee", "Common across German and Dutch employers."),
            Pick("greenhouse", _GLOBAL_BOARDS),
            Pick("workday", "The large German industrials and their subsidiaries."),
            Pick("smartrecruiters", "Founded in Germany and widely used by enterprises here."),
            Pick("linkedin", _LINKEDIN),
        ),
        note=(
            "The federal Arbeitsagentur has the most complete German listing of all, but "
            "its public API is not currently usable without credentials that rotate, so it "
            "is deliberately not included rather than shipped broken."
        ),
    ),
    Region(
        code="nl",
        name="Netherlands and Belgium",
        summary=(
            "Recruitee is Dutch and is everywhere here, which makes this one of the "
            "better-covered regions without needing a single key."
        ),
        picks=(
            Pick("recruitee", "Dutch-built and very widely used by employers here."),
            Pick("arbeitnow", "EU roles with visa sponsorship flagged."),
            Pick("jobicy", "Remote roles open across Europe.", {"geo": "emea"}),
            Pick("adzuna", "Good Benelux coverage.", {"countries": ["nl"]}),
            Pick("workable", "Common at Dutch and Belgian scale-ups."),
            Pick("greenhouse", _GLOBAL_BOARDS),
            Pick("workday", "Multinationals with Amsterdam and Brussels offices."),
            Pick("linkedin", _LINKEDIN),
        ),
    ),
    Region(
        code="fr",
        name="France",
        summary=(
            "No free French job API is usable today, so this pack leans on the aggregators "
            "and on company boards, which French scale-ups do use."
        ),
        picks=(
            Pick("jobicy", "Remote roles open to French candidates. No key.", {"geo": "france"}),
            Pick("arbeitnow", "EU roles, no key, with visa sponsorship flagged."),
            Pick("adzuna", "The best French coverage available keylessly.", {"countries": ["fr"]}),
            Pick("jooble", "Adds listings the above misses."),
            Pick("workable", "Common at French scale-ups."),
            Pick("recruitee", "Used across French and Benelux employers."),
            Pick("greenhouse", _GLOBAL_BOARDS),
            Pick("workday", "The large French corporates."),
            Pick("linkedin", _LINKEDIN),
        ),
        note=(
            "France Travail publishes a full public API but it requires an OAuth "
            "application registration, which is more than this app asks of anyone. If you "
            "want it, say so and it can be added."
        ),
    ),
    Region(
        code="ca",
        name="Canada",
        summary="Strong aggregator coverage, and most US company boards hire into Canada too.",
        picks=(
            Pick("jobicy", "Remote roles open to Canadian candidates. No key.", {"geo": "canada"}),
            Pick("adzuna", "Good Canadian coverage.", {"countries": ["ca"]}),
            Pick("jooble", "Adds French-language Quebec listings."),
            Pick("greenhouse", _GLOBAL_BOARDS),
            Pick("lever", _GLOBAL_BOARDS),
            Pick("ashby", "Startups hiring across North America."),
            Pick("workday", "Canadian banks, telecoms and universities all use it."),
            Pick("indeed", "Indeed is strong in Canada. Needs a login."),
            Pick("linkedin", _LINKEDIN),
        ),
    ),
    Region(
        code="au",
        name="Australia and New Zealand",
        summary=(
            "Seek dominates locally and has no open API, so this pack works around it with "
            "aggregators and company boards."
        ),
        picks=(
            Pick(
                "jobicy",
                "Remote roles open to Australian candidates. No key.",
                {"geo": "australia"},
            ),
            Pick("adzuna", "The best keyless Australian coverage.", {"countries": ["au"]}),
            Pick("jooble", "Adds New Zealand listings."),
            Pick("greenhouse", _GLOBAL_BOARDS),
            Pick("lever", _GLOBAL_BOARDS),
            Pick("workday", "The Australian banks, miners and universities."),
            Pick("workable", "Common at Australian small and mid-size employers."),
            Pick("indeed", "Broad local coverage. Needs a login."),
            Pick("linkedin", _LINKEDIN),
        ),
    ),
    Region(
        code="sg",
        name="Singapore and South-East Asia",
        summary=(
            "Regional headquarters hiring is mostly done on the global company boards, "
            "which makes them unusually valuable here."
        ),
        picks=(
            Pick("jobicy", "Remote roles open across Asia-Pacific. No key.", {"geo": "apac"}),
            Pick("jooble", "The broadest keyed coverage for the region."),
            Pick("adzuna", "Singapore only, but reliable.", {"countries": ["sg"]}),
            Pick("greenhouse", _GLOBAL_BOARDS),
            Pick("lever", _GLOBAL_BOARDS),
            Pick("ashby", "Startups with Singapore and regional roles."),
            Pick("workday", "Regional headquarters of large multinationals."),
            Pick("linkedin", _LINKEDIN),
        ),
    ),
    Region(
        code="ae",
        name="Gulf states",
        summary=(
            "Gulf hiring is concentrated in multinational subsidiaries and a few local "
            "portals, so company boards and aggregators do most of the work."
        ),
        picks=(
            Pick("jobicy", "Remote roles open across the wider region. No key.", {"geo": "emea"}),
            Pick("jooble", "The best keyed coverage across the Gulf."),
            Pick("workday", "The multinationals and the large local groups."),
            Pick("greenhouse", _GLOBAL_BOARDS),
            Pick("smartrecruiters", "Large enterprises hiring in the region."),
            Pick("foundit", "Formerly Monster Gulf. Needs a login."),
            Pick("linkedin", _LINKEDIN),
        ),
    ),
    Region(
        code="ie",
        name="Ireland",
        summary=(
            "Almost every large technology employer runs its EMEA hiring out of Dublin, so "
            "the company boards are the strongest route in."
        ),
        picks=(
            Pick("jobicy", "Remote roles open to Irish candidates. No key.", {"geo": "ireland"}),
            Pick("greenhouse", "The Dublin EMEA offices post here first."),
            Pick("lever", _GLOBAL_BOARDS),
            Pick("ashby", "Startups with Dublin roles."),
            Pick("workable", "Common at Irish small and mid-size employers."),
            Pick("jooble", "Broad Irish aggregation."),
            Pick("workday", "The large employers and the multinational subsidiaries."),
            Pick("linkedin", _LINKEDIN),
        ),
    ),
)

_BY_CODE = {region.code: region for region in REGIONS}


def get(code: str) -> Region | None:
    return _BY_CODE.get((code or "").strip().lower())


def resolve(code: str) -> Region:
    """The requested pack, or India, which is the default."""
    return get(code) or _BY_CODE[DEFAULT_REGION]


def all_regions() -> tuple[Region, ...]:
    return REGIONS
