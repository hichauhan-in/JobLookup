# JobLookup

**A local-first job-search workspace with explainable matches and optional AI.**

Create a profile or upload a resume, choose your target roles and locations,
then search public feeds and employer boards. Matches show the role alignment,
skill evidence, eligibility conflicts, and missing information separately.

Search and ranking work without an AI connection. Connect GitHub Copilot through
VS Code or its CLI, a local model, Anthropic, or an OpenAI-compatible API for
explicit resume analysis, job reviews, and tailoring. There is no automatic
fallback to a different provider.

The React/TypeScript interface has three primary views: **Matches**,
**Applications**, and **Your profile**. Connections, sources, and history live
under **Settings**. The compiled frontend is included, so normal use requires
only the Python launcher, not Node.js.

---

## Contents

**Getting started**
- [Install it (once)](#install-it-once)
- [Connect a model (once)](#connect-a-model-once)
- [Your first search](#your-first-search)
- [Every time after that](#every-time-after-that)
- [Sharing it](#sharing-it)

**Reference**
- [Where the jobs come from](#where-the-jobs-come-from)
- [How the matching works](#how-the-matching-works)
- [What it will not do](#what-it-will-not-do)
- [Settings](#settings)
- [What gets sent where](#what-gets-sent-where)
- [Project layout](#project-layout)
- [Hosted multi-user mode](#hosted-multi-user-mode)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

---

# Getting started

## Install it (once)

**Double-click `Start JobLookup.cmd`.**

That is the whole instruction. The launcher does the rest:

| Step | What happens |
| --- | --- |
| 1 | Finds Python, and installs it via winget if it is missing (no admin rights needed) |
| 2 | Creates a private Python environment in `.venv\` — nothing global changes |
| 3 | Installs the Python packages into it |
| 4 | Installs the **Copilot bridge** into VS Code |
| 5 | Adds a **JobLookup** shortcut to the Start Menu |
| 6 | Starts the server and opens <http://127.0.0.1:8770> |

The first run takes a minute or two. When it finishes you will see:

```
  JobLookup is running at http://127.0.0.1:8770
  Press Ctrl+C to stop.
```

To stop it later, press **Ctrl+C** in its terminal. Closing the browser tab does
not stop the local server.

**One manual step, and only if VS Code was already open** when you first ran it:
VS Code will not have noticed the new bridge extension. Press
<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> and run **`Developer: Reload
Window`**. JobLookup tells you when this is needed, and the prompt clears itself
once VS Code has reloaded.

> **If Windows says the file is blocked** because it came from another computer:
> right-click `Start JobLookup.cmd` → Properties → tick **Unblock** → OK.

### Confirm it is healthy

The top bar shows whether the local workspace is reachable. Test an AI provider
from **Settings > AI connection > Save & test**. From a terminal:

```powershell
.\.venv\Scripts\python.exe -m joblookup doctor
```

Every failing check prints the exact command that fixes it.

---

## Connect a model (once)

AI is optional. Local document extraction and evidence-based ranking work
without it. Configure a provider under **Settings > AI connection** to enable
AI resume analysis, job reviews, and tailored drafts. API keys entered there are
stored separately from configuration and scoped to their endpoint.

> A Copilot subscription is licensed for use *through* approved clients, not as a
> general-purpose API key. JobLookup does not invent a way around that. It uses
> VS Code's Language Model API, which is the same route every Copilot-powered
> extension uses — quota, policy and telemetry all behave normally.

### Option A — GitHub Copilot via VS Code *(recommended, already set up)*

Open VS Code. You should see a **JobLookup** indicator in the status bar, and the
indicator in JobLookup should name a model.

**If it is not connected, JobLookup tells you exactly why.** A banner appears
with the keystrokes for your specific situation — extension missing, VS Code
needs reloading, or consent not yet given. It re-checks every few seconds and
disappears on its own.

The usual case is a reload:

1. Switch to **VS Code**
2. Press <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd>
3. Run `Developer: Reload Window`

If VS Code then asks for permission, accept it — an extension cannot use Copilot
models until you do, and that dialog only appears in response to a command you
invoked. You can trigger it yourself with `JobLookup Bridge: Authorise Copilot
Access`.

**Keep a VS Code window open when requesting a Copilot AI action.** Searching,
local resume extraction, evidence scoring, and tracking do not need a model.
AI analysis, reviews, and tailoring use the selected connection explicitly.

To install or remove the bridge by hand: `.\scripts\install-bridge.ps1` and
`.\scripts\install-bridge.ps1 -Uninstall`.

### Option B — GitHub Copilot via the CLI

Works without VS Code:

```powershell
npm install -g @github/copilot
copilot          # sign in once, then exit
```

Then pick it in **Settings → Language model**.

Two honest caveats:

- **Slower and more expensive.** Each call spawns a process and ships the CLI's
  large agent system prompt, so even a small request bills tens of thousands of
  input tokens.
- **Intermittently unreliable for bulk text work.** Being a coding agent, it
  sometimes replies *"No material was provided"* instead of doing the work, with
  a prompt that succeeded moments earlier. JobLookup detects this and retries;
  the bridge does not have the problem at all.

### Option C — a local model, free

**Settings → Language model → Provider → Ollama** points JobLookup at a local
server. Nothing leaves the machine at all, and it is the easiest way to get
**real embeddings**, which upgrades recall from keyword matching to vector
similarity:

```powershell
ollama pull qwen2.5:14b
ollama pull bge-m3          # the embedding model
```

A laptop-sized model is noticeably weaker than Copilot at judging fit, so this is
a privacy choice rather than a quality one.

### Option D — another provider

The same dropdown offers OpenAI, Azure OpenAI, Anthropic Claude, Google Gemini,
OpenRouter, or any internal OpenAI-compatible gateway. Whatever you pick becomes
the one provider in use, and only its own fields are shown; choosing a preset
fills in the endpoint and auth style for you.

Set the API key as an environment variable before starting — it is never written
to a config file:

```powershell
$env:JOBLOOKUP_OPENAI_API_KEY = "<your key>"
.\scripts\run.ps1
```

**Azure OpenAI is usually the right answer for a governed corporate setup** —
your data stays in your tenant and the usage is auditable.

---

## Your first search

### 1. Add your CVs

Open **Your profile > Documents > Choose files**. PDF, DOCX, TXT, and Markdown
documents are read locally. Review the extracted skills and correct or add
anything missing. The local extractor recognizes a finite skill vocabulary; it
does not infer every skill or parse scanned images. The document's AI action
requests a richer analysis from your selected provider, explicitly.

### 2. Say what you are looking for

Add target roles, preferred locations, working arrangements, employment types,
experience, and exclusions. Save the profile. Manual edits survive subsequent
document extraction. Portfolio links are retained as profile information; the
app does not crawl those links automatically.

### 3. Choose your sources

Open **Settings > Job sources**. Choose a region and **Use recommended**, or
configure individual public feeds, employer boards, and keyed APIs. Employer
boards take company names; Workday takes the careers-page URL. The source
configuration dialog contains the relevant fields and credential links.

Ready, enabled sources participate in searches, including optional portals
after you enable portal access and acknowledge each portal's restrictions.
The employer catalogue provides starting suggestions, not a guarantee that a
source remains available.

### 4. Run a search

Open **Matches**, choose the posting-age window, and press **Find jobs**.
Public sources are fetched concurrently, normalized, deduplicated, and ranked
locally. Progress remains visible while you navigate; the task can be stopped.
Source counts and failures are recorded under **Settings > Search history**.

### 5. Read the matches

**Recommended** contains relevant postings with sufficient local evidence and
no detected preference conflicts. **Needs review** separates missing location,
date, or skill evidence. **All postings** includes excluded jobs with their
reasons. Hidden jobs have a separate recoverable view.

Open **View match > Fit evidence** for the score components and exact posting
quotes. Scores measure the published evidence, not the probability of being
hired. Country/city recognition and explicit requirement parsing are
conservative, not exhaustive; confirm eligibility with the employer.

### 6. Tailor and track

The detail drawer has optional **AI review** and **Resume** tabs. Tailoring uses
the selected base document and produces a draft and interview-preparation notes.
Review generated material before using it. Save a job to track it under
**Applications**.

The **Applications** screen is where you move things along. Each row has its own
status picker, so marking something applied or rejected takes one click and never
leaves the list, and **Remove** stops tracking a role you have gone off. Removing
a tracked role leaves the posting itself in your matches.

### Starting over

Use **Clear stored matches** in the Matches toolbar to remove untracked
postings. Tracked applications, resumes, profile, sources, and history are
preserved. Application tracking can be cleared separately without deleting
postings. Both operations require confirmation.

---

## Every time after that

**Double-click `Start JobLookup.cmd`, or search the Start Menu for JobLookup.**

Startup takes a couple of seconds — the setup steps only run when something is
missing. Nothing to reinstall, nothing to reauthorise.

**If you use the VS Code bridge**, keep an authorized VS Code window open for
AI actions. Search and local ranking do not require it.

To stop it, press <kbd>Ctrl</kbd>+<kbd>C</kbd> in the terminal, or close it.
Everything you have collected lives in `workspace\` and stays there between runs.

### Switches

```powershell
.\scripts\run.ps1 -Port 9000        # use a different port
.\scripts\run.ps1 -NoBrowser        # do not open a browser
.\scripts\run.ps1 -NoBridge         # do not touch the VS Code extension
.\scripts\run.ps1 -WithPortals      # also install Playwright (large download)
.\scripts\run.ps1 -Doctor           # run the health checks and exit
.\scripts\run.ps1 -Reinstall        # rebuild the Python environment
```

---

## Sharing it

```powershell
.\scripts\package.ps1 -Zip
```

Produces `dist\joblookup-<version>.zip` — around 200 KB, because the only things
in it are text. The recipient extracts it and double-clicks
`Start JobLookup.cmd`; the first run builds a private Python environment inside
that folder and installs the bridge into their VS Code.

**The bundle is verified before it is written.** The packager walks the source
tree and refuses to produce a bundle that is missing any file the app opens at
runtime — the Python package, the web UI, the database schema, the portal
selector files, the bridge extension and the launcher. Because the check is
derived from the source rather than a hand-written list, adding a screen or a
portal cannot silently be left out of the next bundle. It also refuses to ship
if your own data somehow ended up inside.

What travels:

| Included | Why |
| --- | --- |
| `joblookup\` | The application, including `web/`, `db/schema.sql` and the portal YAML |
| `vscode-bridge\` | The Copilot bridge, so the recipient gets it installed automatically |
| `scripts\` | The launcher, the bridge installer, this packager |
| `config\default.yaml` | The defaults. Their own `local.yaml` is created on first change |
| `tests\` | So `pytest` works on their machine too |
| `pyproject.toml` | What to install |
| `.gitignore` | Stops them committing their own CVs if they `git init` |
| `README.md`, `SETUP.txt` | This file, and a short one written for the recipient |

Deliberately **excluded**, so you never hand someone your own data:

| Excluded | Why |
| --- | --- |
| `workspace\` | Your CVs, postings, scores and applications |
| `config\local.yaml` | Your provider, model and tuning choices |
| `.venv\` | Not relocatable; absolute paths are baked into it |

API keys are never in the bundle either, because they are never in a file the
bundle would reach — they live in Windows Credential Manager or in an
owner-only file outside the project.

**A Git repository is the better channel for a team** — `git clone` then
`Start JobLookup.cmd`, and updates are `git pull`. Add `-Offline` to the package
script for machines that cannot reach a package feed; it bundles the Python
packages as wheels, which only works if everyone runs the same Python minor
version.

**Give each person their own copy.** Data lives in `workspace\` next to the
code, not under a user profile, so two people sharing one folder would share one
set of CVs and applications. Their Copilot seat, their API keys and their bridge
are already per-user; only the folder needs separating. If you genuinely need
one shared installation, run it in
[hosted multi-user mode](#hosted-multi-user-mode) behind an authenticating
proxy, which isolates each person's data properly.

---

# Reference

## Where the jobs come from

The Sources screen presents these as four collapsible sections. The country pack
is open when you arrive; **Expand all** opens the rest. Every source has a **?**
that explains, for that specific site, exactly what it wants from you.

### Where are you looking? — the country and remote packs

Not a separate set of sources: a shortlist of the ones below, ordered by what
actually works in one country, with that country's settings filled in. Pick a
country and press **Set up this pack** and it switches on everything in the pack
that can already run, fills in country settings for the rest, and reports what
still needs a free key, a company name or a login. It never enables a source
that needs a login — that stays a deliberate, separate act.

| Pack | What it leans on |
| --- | --- |
| India (default) | Jobicy and RemoteOK work immediately; Adzuna and Jooble once keyed; the global company boards for multinationals; the four Indian portals if you accept a login |
| Remote (anywhere) | The six remote-first boards, and it filters your results down to remote roles |
| United States | The Muse and Jobicy keyless, USAJOBS for federal roles, and almost every company board |
| United Kingdom | Reed above all, then Adzuna, then the company boards |
| Germany, Austria, Switzerland | Personio, which reaches roles nothing else indexes, plus Arbeitnow |
| Netherlands and Belgium | Recruitee, which is Dutch-built and everywhere here |
| France | Jobicy and Arbeitnow keyless, Adzuna and Jooble keyed, plus company boards |
| Canada, Australia and New Zealand, Singapore and South-East Asia, Gulf states, Ireland | A keyless Jobicy region feed, the relevant aggregator, and the company boards |

Every pack turns something on the moment you press the button; there is a test
that enforces it. Picking a pack without pressing the button only changes what
is shown.

### Company job boards — where the good postings are

Greenhouse, Lever, Ashby, Workable, Recruitee, SmartRecruiters, Workday,
Personio. Companies publish their own openings as public JSON. Add a company and
its whole careers page becomes a source.

You add the company's short name exactly as it appears in the address of its
careers page:

| Board | Careers page address | You enter |
| --- | --- | --- |
| Greenhouse | `https://boards.greenhouse.io/stripe` | `stripe` |
| Lever | `https://jobs.lever.co/spotify` | `spotify` |
| Ashby | `https://jobs.ashbyhq.com/linear` | `linear` |
| Workable | `https://apply.workable.com/blueground` | `blueground` |
| Recruitee | `https://bunq.recruitee.com` | `bunq` |
| SmartRecruiters | `https://careers.smartrecruiters.com/Visa` | `Visa` (capitals matter) |
| Personio | `https://getsafe.jobs.personio.de` | `getsafe` |
| Workday | `https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite` | the whole address |

Workday is the odd one out, and worth the exception: it is what most large
employers run their careers site on. Its address carries three parts that cannot
be guessed from a company name, so you paste the address itself and the app pulls
them out. A language segment or a deep link copied from the middle of a search
both work. It is also slower than the other boards, because Workday sends titles
and descriptions separately and each posting costs a second request; the
"Descriptions to fetch per company" setting is that trade-off.

#### Letting the app pick the companies

Nobody has a hundred company names in their head, so the guided setup picks them.
Two things make it worth trusting:

- **Every company in the catalogue was checked against the live API.** Of several
  hundred obvious-looking names tried, well under half actually resolved. Names
  are not guessable, which is the whole reason this exists.
- **It is ranked against you, not a generic top-100.** Each company carries tags,
  which are matched against the skills and titles in your profile, then weighted
  by whether they hire where you are looking and how well they pay. Every
  suggestion shows the reason it was picked, and the full list is shown after
  setup so you can check it.

The picks are spread across boards so no single one dominates. A company that
later leaves its board simply returns nothing and is skipped.

Personio is the other exception: it publishes no description text and no posting
date, so its roles are matched on title, department and seniority alone, and are
never filtered out for being stale.

The **?** next to each board shows these examples in the app, so you do not have
to come back here. A company that has moved to a different board simply returns
nothing and is skipped — try the same name on the other boards.

### Public job APIs — no account, nothing to configure

RemoteOK, Remotive, Arbeitnow, Himalayas, The Muse, Jobicy, Working Nomads, We
Work Remotely. Broad, general-purpose feeds that need nothing from you at all;
five of them are on by default. Jobicy can be narrowed to one region, which the
country packs do for you.

Four of these are remote-only boards, which is worth knowing: if you are not
looking for remote work, the country packs and the company boards matter more.

### Public job APIs — free account

Adzuna, Jooble, USAJOBS, Findwork, Reed. Sign up, paste the key into **Sources** once.
Each one's **?** walks you through where to register, what the key looks like,
and anything unusual it wants — USAJOBS, for instance, requires the email you
registered with to be sent as the user agent, which is why it asks for both.

Keys go into Windows Credential Manager where it is available and into an
owner-only file otherwise. Never into a config file, and never anywhere except
the API they belong to.

### Job portals - optional access

LinkedIn, Indeed, Naukri, Glassdoor, Wellfound, Dice, Instahyre, Cutshort,
Foundit.

Under **Settings > Job sources**, choose **Job portals** or scroll to the portal
section. Three paths are available:

1. **Sign in:** enable Portal access, accept the per-portal restrictions, and
  select **Save & sign in**. Install browser support when prompted. Enter your
  credentials and any verification only on the portal's own browser page, not
  in JobLookup. The window closes after an authenticated page or session signal
  is detected. A profile directory alone never counts as a successful login.
2. **Try without sign-in:** supported connectors can request ordinary public
  listing pages without stored login cookies. This is best effort, not an
  official API or a bypass. At most one listing page and three public detail
  pages are read per run. Full descriptions are used when publicly available;
  incomplete details remain subject to review.
3. **Import job:** paste the posting URL, title, company, and description from
  a job you can access. This requires no automation, browser support, or saved
  account. Unknown dates remain unknown. The posting enters normal matching
  and application tracking with its original portal source.

**Sign-in does not authorize automated access.** LinkedIn and other portals may
restrict automation and can block requests or restrict accounts. Use these
connectors only where your use is permitted. There is no CAPTCHA solving, login
circumvention, account creation, or stealth-browser configuration.

Portal sessions are local to `workspace/browser_profiles`. **Disconnect** deletes
the portal's local browser state and disables it without deleting stored jobs.
Status can expire and selectors can change. **Check access** reports readable
cards or an actionable error; an access block is not reported as an empty result.

Public LinkedIn listings and three full descriptions were readable in a local
smoke test; Indeed returned HTTP 403 and was not retried. This does not guarantee
availability for other sessions, locations, or dates. Signed-in behavior cannot
be verified without the user's own interactive login.

---

## How the matching works

The current pipeline is deterministic and local:

```text
public sources -> normalization and deduplication -> eligibility and evidence -> views
```

The workspace evaluates stored postings against the current profile or selected
search track, not stale AI scores. The `evidence-v2` engine recognizes a bounded
set of related role families, separates management titles, and distinguishes
required, preferred and negated skill mentions. Exact quotations remain visible.
It checks recognized country/city restrictions, working arrangement, employment
type, seniority, explicit experience requirements, exclusions, and posting age.
Optional compensation, sponsorship, working-hours and posting-criteria checks
use explicit evidence. Salary units and currencies must match; no conversion is
invented, and a minimum-only range is not treated as an upper salary bound.

Exact profile and posting content key a bounded assessment cache. Profile or
posting edits invalidate the result immediately; freshness is rechecked at
minute granularity. Unknown fields remain explicit rather than being inferred
as favorable facts. An AI review is separate from these rules and cannot
override a detected eligibility conflict.

### Scoring

| Evidence | Maximum points |
| --- | --- |
| Target-role alignment | 45 |
| Explicit skill coverage | 30 |
| Location eligibility | 10 |
| Seniority alignment | 10 |
| Published date within the selected window | 5 |

A known **Required** preference conflict excludes the posting regardless of points.
**Preferred** constraints influence fit without hard exclusion; **Any** skips the
constraint. Confirmed closure always excludes a posting. Missing
location, date, description, or skill evidence routes it to **Needs review**.
The score is an inspectable heuristic, not a calibrated hiring probability.
Skill and geography dictionaries are deliberately conservative and are not
exhaustive. Legal eligibility and unstated requirements still need human review.

### Daily workflow

- **Search tracks:** use the selector in Matches to create independent role,
  location, source and resume-focused searches. The main career profile is not
  overwritten. Track schedules use your computer's local time, run only while
  JobLookup is running, and catch up once later on the same scheduled day.
- **New & changed:** the inbox tracks posting content separately for each track.
  Opening a posting or marking the current page reviewed acknowledges it.
  Changed descriptions or eligibility data can bring a posting back.
- **Daily brief:** an on-device summary of unseen opportunities and due actions,
  with a Markdown download. No email service or external notification account
  is connected.
- **Relevance labels:** Relevant, Adjacent and Not relevant labels with reasons
  are stored alongside posting/profile snapshots. The benchmark in Settings >
  Workspace reports only this labeled sample, not general recommendation accuracy.
  Label at least 50-100 representative jobs before using it to judge improvements.
- **Application activity:** record recruiter details, interview/follow-up/deadline
  dates, completed actions and status history. Resume history preserves drafts,
  compares them with their source document, and flags newly introduced skill and
  numeric claims for review. Record the submitted version on the application.
  These checks are not a guarantee that generated statements are true.
- **Capture:** preview a public URL, paste a job description or alert email, or
  import an EML/HTML/text file. Confirm the posting fields before saving. The
  optional Chrome/Edge helper is downloadable under Settings > Workspace and
  reads the active tab only when clicked. Installation instructions are included.
- **Backups:** export and preview a portable workspace ZIP under Settings >
  Workspace. Restore requires confirmation, checks file hashes and database
  relationships, creates a safety backup, and pauses restored schedules.
  Connection settings, raw source payloads, and browser sessions are excluded.
  Archives contain personal data and are not encrypted. Limits: 80 MB compressed,
  160 MB expanded, 25 MB per document. Unavailable original files are reported.

### Search coverage and freshness

Query-based connectors account for every role/location combination, with at most
24 combinations per source per run and the configured posting budget. The search
report shows completed, skipped, partial and failed queries, plus fetched,
detailed, recommended and new posting counts. Retry incomplete searches reuses
only unfinished combinations where possible. Completed sources are ingested while
other sources are still running. A blocked portal stops further requests.

Public portal enrichment remains deliberately bounded. Partial listing snippets
stay in Needs review even when long. A public availability check distinguishes a
closed/missing listing, a published JobPosting, and an unverified or blocked page;
a published listing is not a guarantee that applications are still accepted.

### Deduplication

The same role found on five sources becomes one card carrying five links.
Sibling roles at the same company stay separate — a fingerprint of company plus
title plus location, then a narrower near-duplicate pass that refuses to merge
across a seniority, discipline or location difference.

---

## What it will not do

- **It will not apply for you.** Auto-apply produces bad applications and gets
  accounts banned.
- **It will not put skills you do not have on your CV.** Every claimed skill is
  checked against your source CV text; anything unsupported is moved to
  "Currently upskilling" or onto the interview prep sheet. That is enforced in
  code, not just asked for in a prompt.
- **It will not store your portal passwords.** There is no field for one.
- **It will not require a paid API key.** Ever.

---

## What a search costs

Searching and local ranking make **zero model calls**. Public sources can still
have their own API quotas. Optional AI analysis, reviews, connection tests, and
tailoring consume your selected provider's quota. Exact billing belongs in that
provider's dashboard. The former automatic spending dial is not part of the
rebuilt workflow.

## Settings

Everything lives in `config/local.yaml`, written for you by the Settings screen
and left alone by updates. `config/default.yaml` holds the defaults and is
replaced when you update, so do not edit it.


Any value can be overridden for one run with an environment variable named
`JOBLOOKUP_<SECTION>_<KEY>`:

```powershell
$env:JOBLOOKUP_SEARCH_RECENCY_DAYS = "14"
$env:JOBLOOKUP_MATCHING_SCORE_BATCH_SIZE = "4"
```

Settings now has four focused sections: **AI connection**, **Job sources**,
**Search history**, and **Workspace**. Profile preferences are edited in Your
profile. Low-level source pacing, timeouts, and compatibility settings remain
in configuration rather than being presented as dozens of everyday controls.
Legacy model-scoring weights do not control the new local evidence engine.

---

## What gets sent where

| Destination | What reaches it |
| --- | --- |
| Job sources | An ordinary HTTP request. Keyed APIs also receive your target titles and locations as the search query. |
| Your language model | Only on an explicit AI action: relevant profile/job text, or the selected resume for analysis and tailoring. |
| Anywhere else | Nothing. |

With the VS Code bridge, "your language model" means GitHub Copilot through VS
Code, on the same terms as any other Copilot request. With Ollama it means
nothing leaves the machine at all.

Your documents, postings, and application history are stored in `workspace\`.
They are not sent to an AI provider during ordinary search or local ranking.
Explicit AI actions send the necessary text to the provider you selected.

### What reaches JobLookup

There is no login, because the server is yours and it listens only on
`127.0.0.1`. That is not enough on its own, so two things are checked on every
request:

* **The address you asked for.** A web page on any domain can point that domain
  at `127.0.0.1` and become same-origin with JobLookup, which would hand it your
  CVs. The browser cannot forge the `Host` header, so anything not addressed to
  this machine is refused. Starting with `--host` set to something other than
  loopback is a deliberate choice to be reachable, and turns this check off.
* **Where the request came from.** Uploads and form posts cross origins without
  a CORS preflight, so anything that changes state must carry a `Sec-Fetch-Site`
  saying it started here. Command-line clients send no such header and are
  allowed.

Outbound requests are checked too. Sources are third parties and a third party
can answer with a redirect, so each hop is re-checked rather than followed
blindly. Literal loopback, private, and link-local destinations are refused,
and authentication headers are removed on cross-host redirects. This is not a
network sandbox or a guarantee against DNS rebinding; run the tool locally and
use trusted source configurations.

---

## Project layout

```
joblookup/
  llm/            Provider interface: VS Code bridge, Copilot CLI, OpenAI-compatible, Anthropic
  cv/             PDF and DOCX reading, extraction, multi-CV profile merge
  sources/        tier_a (public APIs), ats (company boards), tier_b (logged-in portals), regions.py (country packs), catalogue.py (verified companies)
  matching/       Recall, prefilter, batched scoring, deduplication, the pipeline
  tailor/         CV generation, the style guard, DOCX output
  services/       Crawl orchestration, profile rebuild, secrets, scheduler
  server/         HTTP API, background job queue, WebSocket progress
  web/            The UI: hand-written ES modules, no build step
  db/             SQLite schema and access
  doctor.py       Every health check behind the Diagnostics panel
vscode-bridge/    The VS Code extension that exposes your Copilot seat on localhost
config/           default.yaml (ours) and local.yaml (yours)
tests/            The suite. Ships with the bundle so it runs on any machine.
scripts/          run.ps1, install-bridge.ps1, package.ps1
workspace/        Your data. Gitignored, never packaged.
```

### The bridge

`vscode-bridge/` is a small VS Code extension that starts an HTTP server on
`127.0.0.1` and forwards chat requests to `vscode.lm`. It is plain JavaScript
with no build step, so installing it is a folder copy — no `code` CLI, no admin
rights, no `.vsix`.

| Control | Why |
| --- | --- |
| Binds `127.0.0.1` only | Never reachable from the network |
| Per-session bearer token in `~/.joblookup/bridge.json`, mode 0600 | Another process cannot quietly spend your Copilot quota |
| Constant-time token comparison | The token cannot be guessed a byte at a time |
| Rejects any request carrying `Origin` or `Sec-Fetch-Site` | Blocks a web page attempting DNS rebinding |
| 8 MB body cap | Bounded memory |

The token is regenerated every time the extension starts, so the handshake file
is only valid while that VS Code window is open.

---

## Hosted multi-user mode

Running one copy centrally is a different security model from giving each person
their own local copy. JobLookup supports isolated hosted state, but it **must**
sit behind an authenticating reverse proxy:

```yaml
server:
  host: 0.0.0.0
  multi_user: true
  allowed_origins: ["https://joblookup.example.com"]
```

Set a random upstream secret in the server process:

```powershell
$env:JOBLOOKUP_PROXY_SECRET = "<at least 32 random bytes>"
```

The reverse proxy has four mandatory jobs:

1. Terminate HTTPS and authenticate every request, including WebSocket upgrades.
2. **Remove** any client-supplied `x-joblookup-user` and
   `x-joblookup-proxy-secret` headers.
3. Inject `x-joblookup-user` from a stable, immutable identity-provider subject
   identifier — not a display name or a reusable email address.
4. Inject `x-joblookup-proxy-secret` from proxy configuration, never from the
   browser or an identity claim.

JobLookup rejects hosted API traffic without both values, and hashes the subject
before using it on disk. Browser sign-in for logged-in portals is disabled in
hosted mode, because it would open a window on the server rather than on the
user's machine.

---

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest          # the suite, no network access needed
.\.venv\Scripts\python.exe -m ruff check .    # lint
.\.venv\Scripts\python.exe -m ruff format .   # format
.\.venv\Scripts\python.exe -m joblookup doctor
.\scripts\package.ps1                         # build and verify a bundle
```

Tests cover normalisation, deduplication behaviour, the style guard, config
layering, scoring weights and banding, the prefilter, the storage layer and JSON
recovery from a chatty model. None of them touch the network or a real model.

Frontend source lives under `frontend/src`. Its production build replaces
`joblookup/web` and is served by FastAPI with hashed assets. Normal end users do
not need Node.js; frontend development does.

```powershell
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
node --test vscode-bridge/test/bridge.test.cjs
```

Browser tests use a temporary database, not the saved workspace. Bridge tests
use temporary discovery directories and stub only the VS Code model API.

---

## Troubleshooting

| Symptom | What is happening | Fix |
| --- | --- | --- |
| Sidebar says **No model** | The bridge is not answering | The banner names your exact case. Usually: reload the VS Code window. |
| "The VS Code bridge is not running" | The extension is not installed, or VS Code has not loaded it | `.\scripts\install-bridge.ps1`, then `Developer: Reload Window` |
| "Copilot access has not been authorised" | Consent has not been given | Run `JobLookup Bridge: Authorise Copilot Access` in VS Code |
| A search finds nothing | No sources enabled, or the recency window is too tight | Sources screen; raise `search.recency_days` |
| One source is failing | The API changed, or a key expired | Its row on the Sources screen carries the error |
| A portal returns zero results | The portal changed its layout | **Test selectors**, then edit the YAML it names |
| Scoring is slow | One call per posting, or too many postings reaching the model | Raise `matching.score_batch_size`; lower `matching.prefilter_keep` |
| "The prompt is N tokens but the model accepts M" | The batch is too large for the model's window | Lower `matching.score_batch_size` or `matching.description_chars` |
| Copilot CLI says "no material was provided" | Known intermittent agent behaviour | It retries automatically. Use the VS Code bridge instead. |
| "Almost no text came out of that file" | A scanned PDF has no text layer | Upload the DOCX, or export a text-based PDF |
| Everything looks wrong | — | Settings → Diagnostics. Every failure prints the command that fixes it. |

To wipe collected postings but keep your CVs and profile, delete
`workspace\joblookup.db*` and restart. To start completely fresh, delete
`workspace\`.
