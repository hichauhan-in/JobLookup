"""A catalogue of companies whose job boards are known to work.

Every entry here was fetched from the live API before being written down. That
matters more than it sounds: of the several hundred plausible company names
tried, well under half actually resolved. A name that looks obvious is very
often wrong, which is exactly why nobody should have to guess at them.

Nothing here is permanent. Companies move between boards and close their
listings, so a stale entry simply returns nothing and is skipped, and the
Sources screen can re-check the whole catalogue on demand.

Tags are what let a suggestion be personal: they are matched against the skills
and target titles in your profile, so a data engineer and a designer asking for
the same number of companies get different lists.
"""

# One company per line reads as the table it is; wrapping each entry over four
# lines would quadruple the length and hide the shape of the data.
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: When each entry was last confirmed to answer with at least one posting.
VERIFIED_ON = "2026-08-15"


@dataclass(frozen=True, slots=True)
class Company:
    name: str
    board: str
    #: What the user would otherwise have had to type. A full URL for Workday.
    slug: str
    tags: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    #: 1 pays best and is hardest to get into, 3 is a solid employer.
    tier: int = 2
    #: Openings seen when the entry was verified. A rough size signal only.
    openings: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "board": self.board,
            "slug": self.slug,
            "tags": list(self.tags),
            "regions": list(self.regions),
            "tier": self.tier,
            "openings": self.openings,
        }


def _c(name, board, slug, tags, regions=("us",), tier=2, openings=0):
    return Company(name, board, slug, tuple(tags.split()), tuple(regions), tier, openings)


# --- the catalogue -----------------------------------------------------------
# Grouped by board, and within a board roughly by how well known they are.
COMPANIES: tuple[Company, ...] = (
    # --- Greenhouse ---------------------------------------------------------
    _c(
        "Stripe",
        "greenhouse",
        "stripe",
        "fintech backend infrastructure api payments",
        ("us", "gb", "ie", "sg"),
        1,
        578,
    ),
    _c(
        "Databricks",
        "greenhouse",
        "databricks",
        "data ml ai analytics infrastructure",
        ("us", "in", "gb", "de"),
        1,
        809,
    ),
    _c(
        "Datadog",
        "greenhouse",
        "datadog",
        "infrastructure devops observability backend",
        ("us", "fr", "ie"),
        1,
        424,
    ),
    _c(
        "MongoDB",
        "greenhouse",
        "mongodb",
        "data backend infrastructure database",
        ("us", "in", "gb", "ie"),
        1,
        409,
    ),
    _c(
        "Cloudflare",
        "greenhouse",
        "cloudflare",
        "infrastructure security networking backend",
        ("us", "gb", "sg", "in"),
        1,
        305,
    ),
    _c("Okta", "greenhouse", "okta", "security identity backend saas", ("us", "in", "ca"), 1, 333),
    _c(
        "Pinterest",
        "greenhouse",
        "pinterest",
        "consumer ml frontend mobile data",
        ("us", "ie"),
        1,
        222,
    ),
    _c(
        "Airbnb",
        "greenhouse",
        "airbnb",
        "consumer marketplace backend data design",
        ("us", "in", "ie"),
        1,
        186,
    ),
    _c(
        "Coinbase",
        "greenhouse",
        "coinbase",
        "fintech crypto backend security",
        ("us", "gb", "in"),
        1,
        167,
    ),
    _c("Figma", "greenhouse", "figma", "design frontend product consumer", ("us", "gb"), 1, 162),
    _c(
        "Twilio",
        "greenhouse",
        "twilio",
        "api backend infrastructure communications",
        ("us", "in", "ie"),
        1,
        157,
    ),
    _c("Reddit", "greenhouse", "reddit", "consumer ml backend data", ("us", "ca", "gb"), 1, 151),
    _c("Robinhood", "greenhouse", "robinhood", "fintech backend mobile data", ("us", "gb"), 1, 124),
    _c("Roblox", "greenhouse", "roblox", "gaming backend graphics infrastructure", ("us",), 1, 230),
    _c("Samsara", "greenhouse", "samsara", "iot hardware backend data", ("us", "gb"), 1, 222),
    _c("Scale AI", "greenhouse", "scaleai", "ai ml data infrastructure", ("us",), 1, 211),
    _c(
        "GitLab",
        "greenhouse",
        "gitlab",
        "devops developer-tools backend remote",
        ("us", "gb", "de", "in"),
        1,
        196,
    ),
    _c("Lyft", "greenhouse", "lyft", "consumer marketplace backend data mobile", ("us",), 1, 171),
    _c(
        "Elastic",
        "greenhouse",
        "elastic",
        "data search infrastructure backend remote",
        ("us", "nl", "gb", "in"),
        1,
        257,
    ),
    _c(
        "Celonis",
        "greenhouse",
        "celonis",
        "data analytics enterprise backend",
        ("de", "us", "gb"),
        1,
        257,
    ),
    _c(
        "Fivetran",
        "greenhouse",
        "fivetran",
        "data analytics backend infrastructure",
        ("us", "in", "ie"),
        2,
        230,
    ),
    _c(
        "Instacart",
        "greenhouse",
        "instacart",
        "consumer marketplace ml backend",
        ("us", "ca"),
        1,
        112,
    ),
    _c(
        "Asana",
        "greenhouse",
        "asana",
        "product saas frontend backend design",
        ("us", "gb", "de"),
        1,
        132,
    ),
    _c("Affirm", "greenhouse", "affirm", "fintech backend data payments", ("us", "ca"), 1, 194),
    _c("Brex", "greenhouse", "brex", "fintech backend payments product", ("us", "ca"), 1, 293),
    _c(
        "Flexport",
        "greenhouse",
        "flexport",
        "logistics backend data operations",
        ("us", "nl"),
        2,
        158,
    ),
    _c(
        "HelloFresh",
        "greenhouse",
        "hellofresh",
        "consumer ecommerce operations data marketing",
        ("de", "gb", "us"),
        2,
        372,
    ),
    _c(
        "SumUp",
        "greenhouse",
        "sumup",
        "fintech payments backend mobile",
        ("de", "gb", "br"),
        2,
        380,
    ),
    _c(
        "Toast",
        "greenhouse",
        "toast",
        "fintech payments backend hardware",
        ("us", "ie", "in"),
        2,
        313,
    ),
    _c(
        "Adyen",
        "greenhouse",
        "adyen",
        "fintech payments backend infrastructure",
        ("nl", "us", "sg", "gb"),
        1,
        219,
    ),
    _c(
        "Wolt", "greenhouse", "wolt", "consumer marketplace logistics backend", ("de", "gb"), 2, 239
    ),
    _c("Gusto", "greenhouse", "gusto", "hr fintech backend product", ("us", "ca"), 2, 88),
    _c(
        "Discord", "greenhouse", "discord", "consumer gaming backend infrastructure", ("us",), 1, 50
    ),
    _c(
        "Duolingo",
        "greenhouse",
        "duolingo",
        "consumer education ml mobile design",
        ("us", "de"),
        1,
        70,
    ),
    _c("Chime", "greenhouse", "chime", "fintech backend mobile data", ("us",), 2, 57),
    _c("Monzo", "greenhouse", "monzo", "fintech backend mobile data", ("gb",), 1, 82),
    _c("N26", "greenhouse", "n26", "fintech backend mobile", ("de", "es"), 2, 79),
    _c("Peloton", "greenhouse", "peloton", "consumer hardware fitness mobile", ("us", "gb"), 2, 54),
    _c(
        "Dropbox",
        "greenhouse",
        "dropbox",
        "infrastructure backend product remote",
        ("us", "ie"),
        2,
        35,
    ),
    _c(
        "Postman",
        "greenhouse",
        "postman",
        "developer-tools api backend product",
        ("us", "in"),
        2,
        109,
    ),
    _c(
        "Workato",
        "greenhouse",
        "workato",
        "integration saas backend enterprise",
        ("us", "in", "sg"),
        2,
        152,
    ),
    _c("ZoomInfo", "greenhouse", "zoominfo", "data sales saas backend", ("us", "in", "il"), 2, 104),
    _c("Oura", "greenhouse", "oura", "hardware health consumer mobile", ("us", "fi"), 2, 107),
    _c(
        "Smartsheet",
        "greenhouse",
        "smartsheet",
        "saas product backend enterprise",
        ("us", "gb"),
        2,
        92,
    ),
    _c("Tide", "greenhouse", "tide", "fintech backend mobile", ("gb", "in"), 2, 87),
    _c("Marqeta", "greenhouse", "marqeta", "fintech payments backend api", ("us", "gb"), 2, 44),
    _c("Cabify", "greenhouse", "cabify", "consumer marketplace mobile backend", ("es",), 2, 57),
    _c(
        "FREENOW",
        "greenhouse",
        "freenow",
        "consumer marketplace mobile backend",
        ("de", "gb"),
        2,
        47,
    ),
    _c(
        "New Relic",
        "greenhouse",
        "newrelic",
        "observability infrastructure devops backend",
        ("us", "in", "gb"),
        2,
        61,
    ),
    _c(
        "Fastly",
        "greenhouse",
        "fastly",
        "infrastructure networking backend security",
        ("us", "gb"),
        2,
        54,
    ),
    _c(
        "LaunchDarkly",
        "greenhouse",
        "launchdarkly",
        "developer-tools saas backend",
        ("us", "gb"),
        2,
        46,
    ),
    _c(
        "Qualtrics",
        "greenhouse",
        "qualtrics",
        "saas data product enterprise",
        ("us", "in", "ie"),
        2,
        54,
    ),
    _c("Mercury", "greenhouse", "mercury", "fintech backend product design", ("us", "ca"), 2, 61),
    _c("Carta", "greenhouse", "carta", "fintech saas backend", ("us", "gb", "in"), 2, 59),
    _c("SoFi", "greenhouse", "sofi", "fintech backend mobile data", ("us",), 2, 60),
    _c("Zocdoc", "greenhouse", "zocdoc", "healthtech consumer backend", ("us", "in"), 2, 53),
    _c(
        "GetYourGuide",
        "greenhouse",
        "getyourguide",
        "consumer marketplace travel backend",
        ("de",),
        2,
        55,
    ),
    _c("Checkr", "greenhouse", "checkr", "saas backend data api", ("us",), 2, 47),
    _c("Sweetgreen", "greenhouse", "sweetgreen", "consumer retail operations", ("us",), 3, 46),
    _c(
        "Neo4j",
        "greenhouse",
        "neo4j",
        "data database backend developer-tools",
        ("us", "gb", "se"),
        2,
        42,
    ),
    _c("Salesloft", "greenhouse", "salesloft", "sales saas backend", ("us",), 2, 40),
    _c("Pendo", "greenhouse", "pendo", "product analytics saas", ("us", "in"), 2, 43),
    _c(
        "Lucid Software",
        "greenhouse",
        "lucidsoftware",
        "saas product frontend design",
        ("us",),
        2,
        37,
    ),
    _c(
        "Algolia",
        "greenhouse",
        "algolia",
        "search api developer-tools backend",
        ("fr", "us"),
        2,
        34,
    ),
    _c("Raisin", "greenhouse", "raisin", "fintech backend", ("de", "gb"), 2, 34),
    _c("Solaris", "greenhouse", "solarisbank", "fintech backend api", ("de",), 2, 34),
    _c("Komodo Health", "greenhouse", "komodohealth", "healthtech data ml", ("us",), 2, 35),
    _c(
        "Flatiron Health",
        "greenhouse",
        "flatironhealth",
        "healthtech data ml backend",
        ("us",),
        1,
        34,
    ),
    _c(
        "Amplitude",
        "greenhouse",
        "amplitude",
        "analytics data product saas",
        ("us", "gb", "sg"),
        2,
        31,
    ),
    _c("Betterment", "greenhouse", "betterment", "fintech backend product", ("us",), 2, 31),
    _c("Mixpanel", "greenhouse", "mixpanel", "analytics data product saas", ("us", "in"), 2, 56),
    _c("Bird", "greenhouse", "bird", "consumer hardware operations", ("us",), 3, 37),
    _c("DataCamp", "greenhouse", "datacamp", "education data saas", ("gb", "be"), 3, 31),
    _c(
        "CockroachDB",
        "greenhouse",
        "cockroachlabs",
        "data database backend infrastructure",
        ("us", "gb"),
        2,
        28,
    ),
    _c("GoCardless", "greenhouse", "gocardless", "fintech payments backend", ("gb", "fr"), 2, 28),
    _c("Webflow", "greenhouse", "webflow", "design frontend saas remote", ("us",), 2, 28),
    _c(
        "Contentful",
        "greenhouse",
        "contentful",
        "developer-tools saas backend",
        ("de", "us"),
        2,
        26,
    ),
    _c("PagerDuty", "greenhouse", "pagerduty", "devops observability saas", ("us", "gb"), 2, 26),
    _c("StockX", "greenhouse", "stockx", "ecommerce marketplace consumer", ("us",), 3, 30),
    _c("Glossier", "greenhouse", "glossier", "consumer retail ecommerce marketing", ("us",), 3, 23),
    _c("Coursera", "greenhouse", "coursera", "education consumer product", ("us", "in"), 2, 22),
    _c("Sumo Logic", "greenhouse", "sumologic", "observability data security", ("us", "in"), 2, 22),
    _c("Alloy", "greenhouse", "alloy", "fintech api backend", ("us",), 2, 22),
    _c(
        "Squarespace",
        "greenhouse",
        "squarespace",
        "design frontend consumer saas",
        ("us", "ie"),
        2,
        20,
    ),
    _c(
        "Rent the Runway",
        "greenhouse",
        "renttherunway",
        "ecommerce consumer operations",
        ("us",),
        3,
        20,
    ),
    _c(
        "Modern Health", "greenhouse", "modernhealth", "healthtech consumer backend", ("us",), 2, 19
    ),
    _c("Airtable", "greenhouse", "airtable", "saas product frontend", ("us",), 1, 17),
    _c(
        "Thrive Market",
        "greenhouse",
        "thrivemarket",
        "ecommerce consumer operations",
        ("us",),
        3,
        17,
    ),
    _c(
        "TaskRabbit", "greenhouse", "taskrabbit", "marketplace consumer remote", ("us", "gb"), 3, 16
    ),
    _c("Harry's", "greenhouse", "harrys", "consumer ecommerce retail", ("us",), 3, 16),
    _c(
        "Misfits Market",
        "greenhouse",
        "misfitsmarket",
        "ecommerce operations consumer",
        ("us",),
        3,
        80,
    ),
    _c("Udacity", "greenhouse", "udacity", "education product", ("us", "in"), 3, 17),
    _c("Ritual", "greenhouse", "ritual", "consumer ecommerce health", ("us",), 3, 15),
    _c("Calendly", "greenhouse", "calendly", "saas product remote", ("us",), 2, 12),
    _c("Typeform", "greenhouse", "typeform", "saas design product", ("es",), 2, 12),
    _c("Faire", "greenhouse", "faire", "marketplace ecommerce backend", ("us", "ca", "gb"), 2, 67),
    _c("Lattice", "greenhouse", "lattice", "hr saas product", ("us",), 2, 8),
    _c("TrueLayer", "greenhouse", "truelayer", "fintech api backend", ("gb",), 2, 8),
    _c("Greenhouse", "greenhouse", "greenhouse", "hr saas product", ("us",), 2, 14),
    _c("CircleCI", "greenhouse", "circleci", "devops developer-tools remote", ("us",), 2, 5),
    _c("Bitso", "greenhouse", "bitso", "fintech crypto backend", ("mx",), 2, 9),
    # --- Ashby --------------------------------------------------------------
    _c("OpenAI", "ashby", "openai", "ai ml research backend infrastructure", ("us", "gb"), 1, 746),
    _c("Harvey", "ashby", "harvey", "ai legal backend product", ("us", "gb"), 1, 393),
    _c("Crusoe", "ashby", "crusoe", "ai infrastructure energy hardware", ("us",), 1, 361),
    _c("ElevenLabs", "ashby", "elevenlabs", "ai ml audio backend", ("us", "gb", "pl"), 1, 242),
    _c("Sierra", "ashby", "sierra", "ai product backend", ("us",), 1, 191),
    _c("WHOOP", "ashby", "whoop", "hardware health consumer mobile", ("us",), 2, 172),
    _c("Cohere", "ashby", "cohere", "ai ml research backend", ("ca", "us", "gb"), 1, 144),
    _c("Ramp", "ashby", "ramp", "fintech backend product design", ("us",), 1, 136),
    _c("Decagon", "ashby", "decagon", "ai product backend", ("us",), 1, 134),
    _c("Notion", "ashby", "notion", "product saas frontend design", ("us", "ie", "jp"), 1, 133),
    _c("Zip", "ashby", "zip", "saas procurement backend", ("us",), 2, 127),
    _c("Cursor", "ashby", "cursor", "ai developer-tools backend", ("us",), 1, 114),
    _c("LangChain", "ashby", "langchain", "ai developer-tools backend", ("us",), 2, 107),
    _c("Perplexity", "ashby", "perplexity", "ai search product backend", ("us",), 1, 100),
    _c("Socure", "ashby", "socure", "fintech identity ml backend", ("us", "in"), 2, 100),
    _c("Vanta", "ashby", "vanta", "security compliance saas backend", ("us", "gb"), 2, 96),
    _c("Cognition", "ashby", "cognition", "ai developer-tools research", ("us",), 1, 85),
    _c("Lovable", "ashby", "lovable", "ai developer-tools frontend", ("se",), 1, 74),
    _c("Replit", "ashby", "replit", "developer-tools ai product", ("us",), 2, 75),
    _c("Baseten", "ashby", "baseten", "ai ml infrastructure backend", ("us",), 2, 71),
    _c("Synthesia", "ashby", "synthesia", "ai video product", ("gb",), 1, 63),
    _c("Ashby", "ashby", "ashby", "hr saas product remote", ("us",), 2, 60),
    _c("Suno", "ashby", "suno", "ai audio consumer", ("us",), 1, 59),
    _c("Drata", "ashby", "drata", "security compliance saas", ("us",), 2, 55),
    _c("Supabase", "ashby", "supabase", "developer-tools database backend remote", ("us",), 2, 54),
    _c("Writer", "ashby", "writer", "ai product saas", ("us",), 2, 53),
    _c("Temporal", "ashby", "temporal", "developer-tools infrastructure backend", ("us",), 2, 53),
    _c("Abridge", "ashby", "abridge", "ai healthtech ml", ("us",), 1, 45),
    _c("n8n", "ashby", "n8n", "developer-tools automation backend", ("de",), 2, 39),
    _c("Attio", "ashby", "attio", "saas product frontend", ("gb",), 2, 37),
    _c("Watershed", "ashby", "watershed", "climate data saas", ("us", "gb"), 2, 35),
    _c("Render", "ashby", "render", "infrastructure developer-tools backend", ("us",), 2, 35),
    _c("Linear", "ashby", "linear", "product design frontend remote", ("us",), 1, 33),
    _c("Modal", "ashby", "modal", "ai infrastructure backend", ("us",), 2, 30),
    _c("Coder", "ashby", "coder", "developer-tools infrastructure remote", ("us",), 2, 23),
    _c("Column", "ashby", "column", "fintech backend api", ("us",), 2, 23),
    _c("Oyster", "ashby", "oyster", "hr saas remote", ("us", "gb"), 2, 21),
    _c("Persona", "ashby", "persona", "identity security backend", ("us",), 2, 18),
    _c("Secureframe", "ashby", "secureframe", "security compliance saas", ("us",), 2, 18),
    _c("Granola", "ashby", "granola", "ai product consumer", ("us", "gb"), 2, 17),
    _c("Warp", "ashby", "warp", "developer-tools terminal frontend", ("us",), 2, 16),
    _c("Poolside", "ashby", "poolside", "ai research developer-tools", ("us", "fr"), 1, 15),
    _c("Levelpath", "ashby", "levelpath", "saas procurement backend", ("us",), 2, 14),
    _c("Pylon", "ashby", "pylon", "saas support product", ("us",), 2, 12),
    _c("Plain", "ashby", "plain", "saas support product", ("gb",), 2, 11),
    _c("Resend", "ashby", "resend", "developer-tools api backend", ("us",), 2, 11),
    _c("PostHog", "ashby", "posthog", "analytics developer-tools remote", ("gb", "us"), 2, 11),
    _c("Pika", "ashby", "pika", "ai video consumer", ("us",), 2, 10),
    _c("Browserbase", "ashby", "browserbase", "developer-tools ai infrastructure", ("us",), 2, 8),
    _c("Railway", "ashby", "railway", "infrastructure developer-tools remote", ("us",), 2, 8),
    _c("OpenEvidence", "ashby", "openevidence", "ai healthtech", ("us",), 1, 7),
    _c("Neon", "ashby", "neon", "database developer-tools backend", ("us",), 2, 6),
    _c("Unit", "ashby", "unit", "fintech api backend", ("us",), 2, 5),
    _c("Runway", "ashby", "runway", "ai video ml", ("us",), 1, 4),
    _c("Cedar", "ashby", "cedar", "healthtech fintech product", ("us",), 2, 3),
    # --- Lever --------------------------------------------------------------
    _c(
        "Palantir", "lever", "palantir", "data backend security government ml", ("us", "gb"), 1, 308
    ),
    _c("Zoox", "lever", "zoox", "robotics ml hardware backend", ("us",), 1, 244),
    _c(
        "Spotify",
        "lever",
        "spotify",
        "consumer audio backend data design",
        ("se", "us", "gb"),
        1,
        103,
    ),
    _c(
        "Anchorage Digital", "lever", "anchorage", "fintech crypto security backend", ("us",), 2, 39
    ),
    # --- Workday ------------------------------------------------------------
    _c(
        "NVIDIA",
        "workday",
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        "hardware ai ml gpu infrastructure research",
        ("us", "in", "gb", "de"),
        1,
        2000,
    ),
    _c(
        "Salesforce",
        "workday",
        "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site",
        "saas enterprise backend sales product",
        ("us", "in", "gb", "ie"),
        1,
        1514,
    ),
    _c(
        "Adobe",
        "workday",
        "https://adobe.wd5.myworkdayjobs.com/external_experienced",
        "design saas enterprise backend ml",
        ("us", "in", "gb", "de"),
        1,
        784,
    ),
    _c(
        "HP",
        "workday",
        "https://hp.wd5.myworkdayjobs.com/ExternalCareerSite",
        "hardware enterprise it-operations operations",
        ("us", "in", "gb"),
        2,
        726,
    ),
    _c(
        "GSK",
        "workday",
        "https://gsk.wd5.myworkdayjobs.com/GSKCareers",
        "pharma healthtech data research operations",
        ("gb", "us", "in"),
        2,
        701,
    ),
    _c(
        "Workday",
        "workday",
        "https://workday.wd5.myworkdayjobs.com/Workday",
        "saas enterprise hr backend",
        ("us", "ie", "in"),
        1,
        347,
    ),
    _c(
        "Red Hat",
        "workday",
        "https://redhat.wd5.myworkdayjobs.com/Jobs",
        "infrastructure devops opensource backend remote",
        ("us", "in", "ie", "de"),
        2,
        149,
    ),
    _c(
        "PayPal",
        "workday",
        "https://paypal.wd1.myworkdayjobs.com/jobs",
        "fintech payments backend data security",
        ("us", "in", "gb", "ie"),
        1,
        120,
    ),
    # --- SmartRecruiters ----------------------------------------------------
    _c(
        "Bosch",
        "smartrecruiters",
        "BoschGroup",
        "hardware automotive engineering manufacturing it-operations",
        ("de", "in", "us"),
        2,
        4799,
    ),
    _c(
        "McDonald's",
        "smartrecruiters",
        "McDonaldsCorporation",
        "retail operations marketing",
        ("us",),
        3,
        4,
    ),
    _c(
        "Visa", "smartrecruiters", "Visa", "fintech payments backend data", ("us", "gb", "sg"), 1, 2
    ),
    _c(
        "Clarivate",
        "smartrecruiters",
        "ClarivateAnalytics",
        "data analytics research",
        ("gb", "us", "in"),
        3,
        6,
    ),
    # --- Workable -----------------------------------------------------------
    _c(
        "Blueground",
        "workable",
        "blueground",
        "proptech operations consumer",
        ("gr", "us", "ae"),
        3,
        26,
    ),
    _c(
        "Spotawheel",
        "workable",
        "spotawheel",
        "ecommerce automotive operations",
        ("gr", "pl"),
        3,
        35,
    ),
    _c("Orfium", "workable", "orfium", "media data backend", ("gr", "us"), 3, 22),
    _c("Skroutz", "workable", "skroutz", "ecommerce marketplace backend", ("gr",), 3, 9),
    _c("Persado", "workable", "persado", "ai marketing ml", ("gr", "us"), 3, 3),
    _c("Epignosis", "workable", "epignosis", "education saas product", ("gr",), 3, 4),
    # --- Recruitee ----------------------------------------------------------
    _c("bunq", "recruitee", "bunq", "fintech backend mobile", ("nl",), 2, 11),
    _c(
        "Framestore",
        "recruitee",
        "framestore",
        "media vfx design graphics",
        ("gb", "us", "ca"),
        3,
        50,
    ),
    _c("Livestorm", "recruitee", "livestorm", "saas product remote", ("fr",), 3, 2),
    # --- Personio -----------------------------------------------------------
    _c("Getsafe", "personio", "getsafe", "insurtech fintech backend", ("de",), 3, 7),
)

BOARDS = tuple(dict.fromkeys(company.board for company in COMPANIES))


def by_board() -> dict[str, list[Company]]:
    grouped: dict[str, list[Company]] = {}
    for company in COMPANIES:
        grouped.setdefault(company.board, []).append(company)
    return grouped


def all_tags() -> list[str]:
    return sorted({tag for company in COMPANIES for tag in company.tags})


@dataclass(slots=True)
class Suggestion:
    company: Company
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**self.company.to_dict(), "score": round(self.score, 3), "reasons": self.reasons}
