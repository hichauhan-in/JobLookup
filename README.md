# JobLookup

**Find the jobs worth applying for, using the AI you already have.**

Upload your CVs. JobLookup builds one career profile from them, searches real job
sources, collapses the same role found on five sites into one card, and ranks
what is left against you — with the reasoning shown, and a plain-English split
between gaps you could close in a week and gaps that need years.

It runs entirely on your machine and uses **the GitHub Copilot seat you already
have**, through VS Code's Language Model API. No GPU. No paid API key. Nothing
installed system-wide. Run one script and a browser tab opens.

The ranking is deliberately **stretch-tolerant**. Most people are hired into
roles they have not held before, so a support engineer looking at SRE work should
see those roles, not have them filtered out for a missing keyword.

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

To stop it later, press **Close JobLookup** at the bottom of the sidebar, which
shuts the server down properly. Closing the browser tab on its own leaves it
running in the background.

**One manual step, and only if VS Code was already open** when you first ran it:
VS Code will not have noticed the new bridge extension. Press
<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> and run **`Developer: Reload
Window`**. JobLookup tells you when this is needed, and the prompt clears itself
once VS Code has reloaded.

> **If Windows says the file is blocked** because it came from another computer:
> right-click `Start JobLookup.cmd` → Properties → tick **Unblock** → OK.

### Confirm it is healthy

The indicator at the top-left of the sidebar names the model in use. From a
terminal:

```powershell
.\.venv\Scripts\python.exe -m joblookup doctor
```

Every failing check prints the exact command that fixes it.

---

## Connect a model (once)

JobLookup needs a language model to read your CV and to judge postings. **The
recommended option uses the GitHub Copilot seat you already have, and the
launcher has already installed the bridge for you.**

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

**Keep a VS Code window open while JobLookup is scoring.** Searching, browsing
and tracking all work without a model; reading a CV, scoring postings and
tailoring need one.

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

**Profile → Upload.** Every version you have, not just the latest. Each one is a
partial view of you; merged, they give a fuller picture, and a skill that appears
in most of them is treated as core rather than incidental. Each file also stays
available as a base for tailoring.

Reading a CV takes a few seconds and happens in the background.

### 2. Say what you are looking for

Target titles, locations, work modes, your level, work authorisation, and
anything you never want to see. These are the answers only you can give, and
they are never overwritten by anything read from a document.

If you are not sure what to put in Target titles, press **Suggest roles for me**.
It reads your CV and proposes titles that actually appear in job adverts, split
into what you are ready for now and what would be a step up, each with the reason
it was suggested. Click one to add it. Without a model configured it still works,
falling back to the titles you have held and the obvious steps up from them.

### 3. Choose your sources

The Sources screen has four sections. Every source carries a **?** that opens
step-by-step instructions written for that specific site — where to get its key,
or where to find the company name.

**Start at the top, with "Where are you looking?".** Pick your country, or
**Remote (anywhere)**, and press **Set up this pack**. This is the same set of
sources as the three sections below it, but shortlisted and ordered by what
actually works where you are, with that country's settings filled in. It
switches on everything in the pack that can already run, fills in country
settings for the rest, and tells you plainly what still needs a free key, a
company name or a login. It never enables anything that needs a login. The
default pack is India.

Picking **Remote (anywhere)** also changes what you get back: any posting not
positively identified as a remote role is dropped before it is scored. There is
also an **Only show remote roles** switch beside the country, so "India, but
only roles I can do from home" is a combination you can ask for directly.

**Then add company boards.** Open the careers page of a company you would
actually like to work for, take the company's short name out of the address, and
paste it into **Sources → Company job boards**. For
`https://boards.greenhouse.io/stripe` you enter `stripe`. These postings are the
freshest and cleanest available anywhere — no aggregator lag, full descriptions,
and the apply link goes straight to the employer. This is the single
highest-value thing you can do here, and it is worth revisiting whenever you
think of another company.

**If no companies spring to mind**, press **Not sure which companies to watch?**
at the top of Sources and let it pick. It ranks a catalogue of employers against
your CV and what you are looking for, so a data engineer and a designer get
different lists, and adds the ones that fit to the right boards. Every company
in that catalogue was fetched from the live API before being written down.

Workday is the exception: it is the board most large employers use, and it is
addressed by pasting the whole careers page address rather than a short name.

The keyless public feeds are already on and need nothing.

### 4. Run a search

**Dashboard → Run search.** Progress streams live. Sources are fetched in
parallel, results are normalised and deduplicated, and then matching runs.

The search card carries the two dials worth reaching for mid-search, so a small
change does not mean a trip to Settings:

- **How far back to look** — 24 hours through to a month.
- **How deep to search** — a slider from Glance to Exhaustive. It sets how many
  postings reach the model, and each stop tells you the rough cost in model
  calls, which is the number that decides whether a search is worth it.
- **Remote only**, and **Keep these**. Leave the last one off and your choices
  apply to that one search; turn it on and they become your defaults.

Every search is recorded under **History**, along with the postings it produced.
You can reopen any run's results, delete a single run, or clear the lot. Deleting
history never deletes postings, scores or applications — it only forgets that a
particular search happened.

### 5. Read the matches

**Matches** shows your most recent search by default, because that is almost
always what you want to look at. The selector next to the age filter switches to
any earlier search, or to **Everything collected** to look across all of them.

Filter by band and age. Open one to see the three fit bars, the reasoning, the
skills you already have, and the gaps split into "about a week" and "years".

### 6. Tailor and track

On a posting you like, **Tailor for this job** rewrites your CV for it using only
what your CV already contains, then strips the wording that makes writing read as
machine generated. You get a `.docx`, a Markdown copy, and an interview prep
sheet carrying everything you could not honestly claim.

Set a status on the posting and it appears under **Applications**.

---

## Every time after that

**Double-click `Start JobLookup.cmd`, or search the Start Menu for JobLookup.**

Startup takes a couple of seconds — the setup steps only run when something is
missing. Nothing to reinstall, nothing to reauthorise.

**If you use the VS Code bridge**, have a VS Code window open before scoring.

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

Nobody has a hundred company names in their head, so **Not sure which companies
to watch?** picks them. Two things make it worth trusting:

- **Every company in the catalogue was checked against the live API.** Of several
  hundred obvious-looking names tried, well under half actually resolved. Names
  are not guessable, which is the whole reason this exists.
- **It is ranked against you, not a generic top-100.** Each company carries tags,
  which are matched against the skills and titles in your profile, then weighted
  by whether they hire where you are looking and how well they pay. Each
  suggestion shows the reason it was picked.

The picks are spread across boards so no single one dominates, and by default
they are added to whatever you already have rather than replacing it. A company
that later leaves its board simply returns nothing and is skipped.

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

### Portals that need a login — off by default

LinkedIn, Indeed, Naukri, Glassdoor, Wellfound, Dice, Instahyre, Cutshort,
Foundit.

> **Read this before enabling any of them.** These portals prohibit automated
> access in their terms of service. Using them can get your account restricted or
> permanently banned, and in some jurisdictions carries further legal exposure.
> The design minimises the risk but cannot remove it.
>
> JobLookup never sees or stores your password: you sign in yourself in a visible
> browser window, once, and the session cookie stays in a local profile directory.
> There is no CAPTCHA solving and no 2FA circumvention. Requests are paced with
> randomised human-scale delays, page counts are bounded, and there is a daily run
> cap plus a global kill switch.
>
> Every portal is off until you enable it *and* explicitly acknowledge the risk,
> and Playwright is not even downloaded until you ask for it. Start with the
> public APIs and the company boards; they will likely give you more good
> postings than scraping ever will.

Portal selectors live in `joblookup/sources/tier_b/portals/*.yaml`. When a portal
changes its layout, press **Test selectors**: it opens a real browser and reports
how many nodes each selector matched, so you fix a YAML file rather than Python.

---

## How the matching works

Three stages, each cheaper than the one after it. The shape is the whole cost
story.

```
everything stored  →  recall  →  prefilter  →  the model  →  bands
   (thousands)        (~300)      (~120)       (~10 calls)
```

**1 · Recall — free, no model.** SQLite's full-text index, ranked by BM25 with
the title weighted far above the body. If the selected provider happens to offer
embeddings (a local Ollama server, or an OpenAI-style endpoint you configured),
cosine similarity is used instead because it is better. Copilot has no embeddings
API, so with the default setup this stays lexical — and that is fine, not a
degraded mode.

**2 · Prefilter — free, no model.** Applies the rules *you* stated: work mode,
seniority range, exclusions, recency, and the remote-only rule if you picked the
Remote pack. A model call that concludes "this Berlin-only role is not for you,
you said remote in the UK" is a call that never needed to happen. Nothing
requiring judgement happens here.

**3 · The model — batched.** A dozen postings are judged in one call. The reply
is keyed by the posting id, never by position, so a model that drops or reorders
an entry costs that one score and nothing else; anything missing is retried
alone. Scores are cached against the profile version, so re-running does not
re-spend.

Set `matching.score_batch_size` to `1` for maximum accuracy at roughly twelve
times the cost, or raise `matching.prefilter_keep` for wider coverage. Every
number in that diagram is a setting.

### Scoring

Three dimensions, not one:

| Dimension | Question | Weight |
| --- | --- | --- |
| Direct fit | Have you already done this exact work? | 0.45 |
| Transferable fit | Do your existing skills carry over? | 0.40 |
| Growth fit | Is this a realistic next step? | 0.15 |

Transferable is weighted heavily on purpose. The composite becomes a band —
**Strong**, **Good**, **Stretch** — with a plain-English reason and gaps split
into "about a week" and "years". A genuine hard stop (visa, clearance, a legally
mandatory licence) sets a blocker and rules the posting out regardless of score.
An unfamiliar technology is not a blocker.

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

The Settings screen exposes every number the app uses to make a judgement. Each
one is its own row with a plain-English explanation of what changing it does.

It opens on **Basic**, which is the ten or so settings people actually change.
**Advanced** is the same controls with nothing left out, grouped by what they
affect. Nothing is hidden from you in Basic; it is a shorter list, not a
different one. The **Language model** card sits above both tabs, since it is the
one setting everything else depends on, and clicking the model name in the
sidebar takes you straight to it.

| Group | Covers |
| --- | --- |
| Language model | Provider, model, reasoning effort, context window, request timeout |
| Searching | Recency window, per-source caps, pacing, timeouts, archiving |
| How many model calls to spend | Recall depth, prefilter, batch size, description length, concurrency, retries |
| What counts as a good match | The three fit weights and the three band thresholds |
| Duplicate detection | Title and description similarity, whether location must match |
| CV tailoring | Enrichment level, bullets per role, style guard, upskilling section, output format |
| Logged-in portals | Action delays, pages per run, daily cap, navigation timeout, headless |
| Vector recall | Whether to use embeddings, which model, batch size, timeout, recall mode |
| Scheduled searches | On/off, hour, minute |

The defaults are meant to be good enough that you never open that screen. It is
there because "good enough by default" is not the same as "right for you".

---

## What gets sent where

| Destination | What reaches it |
| --- | --- |
| Job sources | An ordinary HTTP request. Keyed APIs also receive your target titles and locations as the search query. |
| Your language model | Your merged profile summary and the job descriptions being scored. When tailoring, also the text of the CV you selected. |
| Anywhere else | Nothing. |

With the VS Code bridge, "your language model" means GitHub Copilot through VS
Code, on the same terms as any other Copilot request. With Ollama it means
nothing leaves the machine at all.

Your CVs, the postings, the scores and your application history live in
`workspace\` and are never uploaded anywhere.

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

The web UI has no build step: edit a file under `joblookup/web/` and reload the
browser. Static files are served with `no-cache`, so a reload always picks up
your change rather than a stale copy.

Layout is built from a small set of primitives in `joblookup/web/js/dom.js` —
`card`, `accordion`, `settingRow`, `rows`/`splitRows`, `toggle`, `chipToggle`.
Use those rather than a one-off flex container, so a new screen inherits the
same spacing as every other one.

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
