// Settings: which model answers, how hard the app works, and what is wrong.
//
// Every number the app uses to make a judgement is exposed here. The defaults
// are meant to be good enough that nobody has to touch them, and the controls
// are here because "good enough by default" is not the same as "right for you".
//
// The provider is a single dropdown rather than a list of competing panels.
// Only one model answers at a time, so only one set of fields is ever relevant;
// showing the other nine is noise pretending to be choice.

import { api } from "../api.js";
import { app } from "../app.js";
import { accordion, card, el, field, mount, settingRow, spinner, splitRows, toggle } from "../dom.js";
import { humanTokens } from "../format.js";
import { fail, ok } from "../notify.js";

const EFFORTS = ["", "none", "minimal", "low", "medium", "high", "xhigh", "max"];

const EFFORT_LABELS = {
  "": "Model default",
  none: "None - fastest, cheapest",
  minimal: "Minimal",
  low: "Low",
  medium: "Medium - balanced",
  high: "High",
  xhigh: "Very high",
  max: "Maximum - slowest, most thorough",
};

// Plain sizes rather than raw token counts, which mean nothing to most people.
const CONTEXT_WINDOWS = [
  ["", "Model default - recommended"],
  ["8000", "Small - 8,000 tokens"],
  ["16000", "Medium - 16,000 tokens"],
  ["32000", "Large - 32,000 tokens"],
  ["64000", "Very large - 64,000 tokens"],
  ["128000", "Maximum - 128,000 tokens"],
];

const TUNING = [
  {
    title: "Searching",
    subtitle: "How wide to cast the net, and how politely to do it.",
    blurb:
      "These control the fetching stage: which postings are collected from your sources before anything is judged. Nothing here costs a model call, so raising these numbers costs time and bandwidth, never quota.",
    fields: [
      ["search.recency_days", "Only fetch postings newer than", "number",
        "In days. 7 is the useful window: most postings are filled or closed within a month, and a stale listing wastes an application. Raise to 30 if your field moves slowly or your sources are quiet."],
      ["search.max_jobs_per_source", "Maximum postings per source", "number",
        "A ceiling so one enormous source cannot drown out the rest. 200 is generous; a source that hits it is usually a job board rather than a company."],
      ["search.max_concurrent_sources", "Sources fetched at once", "number",
        "How many sources are contacted in parallel. 4 keeps a full search brief without hammering anything. Raise it for speed on a fast connection; lower it to 1 if your network is unreliable."],
      ["search.min_request_interval_s", "Minimum seconds between requests", "number",
        "A politeness floor applied per website. 1 second is safe everywhere. Below that the free APIs start refusing you, and a source that rate-limits you contributes nothing at all."],
      ["search.http_timeout_s", "Request timeout", "number",
        "In seconds. How long to wait for a source before giving up on it and moving on. 30 is patient enough for a slow board without stalling the whole search."],
      ["search.min_description_chars", "Ignore descriptions shorter than", "number",
        "In characters. A posting with a two-line description cannot be judged fairly, so it is dropped rather than scored badly. 120 is roughly two sentences. Set to 0 to keep everything."],
      ["search.archive_after_days", "Archive postings not seen for", "number",
        "In days. When a posting stops appearing in its source it has almost certainly closed. After this long it moves out of your matches but stays in the database, so nothing is lost."],
    ],
  },
  {
    title: "How many model calls to spend",
    subtitle: "The single biggest lever on speed and on your Copilot quota.",
    blurb:
      "Matching runs in three stages. Recall and prefiltering are free and narrow thousands of postings down to a shortlist; only that shortlist reaches the model. These numbers decide how big the shortlist is, which is what a search actually costs you.",
    fields: [
      ["matching.recall_top_k", "Candidates pulled from the index", "number",
        "Stage one, free. How many postings the keyword or vector search hands on. 400 casts a wide net. This reads a search index, not the model, so it costs nothing but a moment."],
      ["matching.recall_min_score", "Minimum recall score to consider", "number",
        "Between 0 and 1, measured against the best hit in that run. 0.2 means 'at least a fifth as relevant as the strongest match'. Raise towards 0.5 for a tighter, smaller shortlist; lower towards 0 to let weaker text matches through."],
      ["matching.prefilter_enabled", "Apply your own rules before scoring", "boolean",
        "Stage two, free. Drops postings that break rules you already stated on the Profile screen - wrong work mode, far too senior, an excluded company, too old. Turning this off sends everything to the model and costs considerably more."],
      ["matching.prefilter_keep", "Postings that reach the model", "number",
        "The shortlist size, and the number that actually costs you. 120 postings at the default batch size is about 10 model calls. Halve it to halve the cost of a search; raise it if you feel good roles are being missed."],
      ["matching.score_batch_size", "Postings judged per model call", "number",
        "How many postings go into one request. 12 is the default. Setting 1 is the most accurate and roughly twelve times the cost. Above about 20 the model starts giving each posting less attention, so accuracy drops."],
      ["matching.description_chars", "Characters of each description sent", "number",
        "How much of each posting the model reads. 4000 is about six paragraphs, enough for requirements and responsibilities. Lower it to fit more postings per call; raise it if long descriptions are being judged on their preamble."],
      ["matching.max_seniority_jump", "Levels above yours still worth showing", "number",
        "In levels, where junior, mid, senior, staff and principal are one apart. 1 shows the next step up. 0 shows only your own level. 2 includes real stretches."],
      ["matching.rescore_existing", "Re-score postings already judged", "boolean",
        "Off means a re-run only judges what is new, which is what you want almost always. Turn it on after changing your CV, your profile or the weights below, so old scores are brought in line with the new rules."],
      ["llm.max_concurrency", "Model requests in flight at once", "number",
        "2 is deliberately modest because Copilot rate-limits and a throttled request is a wasted one. Local models on a strong machine can take 4 or more."],
      ["llm.json_retries", "Retries when a reply will not parse", "number",
        "Models occasionally return prose instead of the structured answer. This is how many times to ask again before giving up on that batch. 2 catches nearly everything."],
    ],
  },
  {
    title: "What counts as a good match",
    subtitle: "How each posting is scored, and where the band boundaries sit.",
    blurb:
      "Every posting gets three scores out of 1: how much of it you have already done, how much of your experience transfers, and whether it is a realistic next step. The three weights below decide how those combine into the single score that sorts your matches, and the thresholds decide which band it lands in. Transferable is weighted heavily on purpose: most people are hired into roles they have not held before, and a scorer that only rewards exact matches shows you the job you already have.",
    fields: [
      ["matching.weight_direct", "Weight: already done this work", "number",
        "How much credit for experience that matches the posting outright. Raise it if you want familiar roles; lower it if your matches feel like your current job again."],
      ["matching.weight_transferable", "Weight: skills transfer across", "number",
        "How much credit for experience that applies without being a direct match. This is the one to raise if you are changing industry or function."],
      ["matching.weight_growth", "Weight: realistic next step", "number",
        "How much credit for a role being a sensible step up rather than something you can already do. Raise it if you want to be stretched."],
      ["matching.strong_threshold", "Score needed for 'strong'", "number",
        "Between 0 and 1. A posting scoring at or above this is badged strong: apply with confidence. 0.75 is demanding on purpose. Lower it if too few roles qualify."],
      ["matching.good_threshold", "Score needed for 'good'", "number",
        "Between 0 and 1, and below the strong threshold. Worth applying to with a tailored CV."],
      ["matching.stretch_threshold", "Score needed for 'stretch'", "number",
        "Between 0 and 1, and below the good threshold. Reachable with effort. Anything below this is filed as a long shot rather than shown as a match."],
    ],
  },
  {
    title: "Duplicate detection",
    subtitle: "The same job on five sites should be one card, not five.",
    blurb:
      "Aggregators republish each other, so the same opening arrives repeatedly under slightly different titles. Two postings at the same company are merged when they look similar enough. The two numbers below are similarity scores between 0 and 1, where 1 means character-for-character identical and 0 means nothing in common.",
    fields: [
      ["matching.dedupe.title_similarity", "Title similarity needed to merge", "number",
        "Between 0 and 1. At 0.85, 'Senior Backend Engineer' and 'Senior Back-end Engineer' merge, but 'Backend Engineer' and 'Frontend Engineer' do not. Lower it if you see the same job twice; raise it if two genuinely different openings are being collapsed into one."],
      ["matching.dedupe.description_similarity", "Description similarity needed to merge", "number",
        "Between 0 and 1, applied to the posting text when the titles are close. 0.9 means the descriptions are nearly the same words, which is what a republished posting looks like."],
      ["matching.dedupe.require_same_location", "Only merge when the location matches", "boolean",
        "On keeps a London and a Manchester opening separate even when everything else is identical. Turn it off if one company posts the same remote role under several city names."],
    ],
  },
  {
    title: "CV tailoring",
    subtitle: "How the rewrite behaves when you tailor a CV to a posting.",
    blurb:
      "Tailoring rewrites your existing CV to speak to one posting. It may never invent experience at any setting: everything it writes has to be traceable to something you actually wrote, and anything unsupported is stripped before you see it.",
    fields: [
      ["tailor.enrichment", "How freely to reframe", "number",
        "0 to 2. At 0 it only reorders and trims what your CV already says. At 1 it rewords your experience in the posting's language. At 2 it draws out implications you left unstated. It never adds a skill you do not have, at any setting."],
      ["tailor.max_bullets_per_role", "Bullets per role", "number",
        "How many achievement lines each job may keep. 5 fits a readable one-page-per-role CV. Lower it for a shorter document."],
      ["tailor.style_guard", "Strip machine-sounding wording", "boolean",
        "Removes the tells that make a CV read as machine-written: em dashes, 'leverage', 'robust', 'spearheaded', 'not just X but Y' and the rest. Leave this on."],
      ["tailor.include_upskilling_section", "Include a 'currently upskilling' section", "boolean",
        "On adds a short honest section naming gaps you are actively closing. Off keeps them out of the CV entirely and sends them to the interview prep sheet instead."],
      ["tailor.output_format", "Output format", "select",
        "DOCX is what employers and applicant tracking systems expect. Markdown is easier to paste into a web form. Both writes two files.",
        ["docx", "markdown", "both"]],
    ],
  },
  {
    title: "Logged-in portals",
    subtitle: "Only relevant once you have enabled a portal on the Sources screen.",
    blurb:
      "These pace the browser automation used for portals like LinkedIn. They exist to make the automation look like a person rather than a script. Lowering the delays is the single most likely way to get an account restricted, and the speed you gain is not worth it.",
    fields: [
      ["tier_b.min_action_delay_s", "Minimum delay between actions", "number",
        "In seconds. Every click and scroll waits a random time between this and the maximum below. 2.5 seconds is roughly how fast a person reads a result."],
      ["tier_b.max_action_delay_s", "Maximum delay between actions", "number",
        "In seconds. The top of the random range. A wide gap between minimum and maximum looks more human than a fixed interval."],
      ["tier_b.max_pages_per_run", "Pages per portal per run", "number",
        "How deep into the results to scroll. 5 pages is plenty; going deeper looks like scraping and reaches older postings anyway."],
      ["tier_b.daily_run_cap", "Runs per portal per day", "number",
        "A hard stop, counted per portal. Even if you run ten searches, each portal is visited at most this many times in a day."],
      ["tier_b.nav_timeout_s", "Page load timeout", "number",
        "In seconds. How long to wait for a portal page before abandoning it."],
      ["tier_b.headless", "Run the browser hidden", "boolean",
        "Off shows a real browser window doing the work, which is easier to trust and less likely to be flagged as automation. On hides it. Leave this off."],
    ],
  },
  {
    title: "Vector recall",
    subtitle: "Optional. Finds roles worded differently from your CV.",
    blurb:
      "Recall is the free first stage that narrows everything stored down to candidates. By default it matches keywords, which misses a posting that says 'data pipelines' when your CV says 'ETL'. Embeddings compare meaning instead, but only work when your provider offers them - GitHub Copilot does not, so this normally stays off and keyword recall is used. That is the normal setup, not a degraded one.",
    fields: [
      ["embeddings.enabled", "Use embeddings when they are available", "boolean",
        "On means use vectors if the provider offers them and fall back to keywords silently if not. It is never an error for this to be on with a provider that cannot do it."],
      ["embeddings.model", "Embedding model", "text",
        "The model that turns text into vectors. Only used with a provider that has an embeddings endpoint, such as a local Ollama server."],
      ["embeddings.batch_size", "Texts embedded per request", "number",
        "How many postings are sent for embedding at once. Higher is faster but uses more memory on the machine running the model."],
      ["embeddings.timeout_s", "Give up on embeddings after", "number",
        "In seconds. If the embedding server is slow, the search falls back to keyword recall rather than stalling."],
      ["matching.recall_mode", "Recall mode", "select",
        "Auto uses vectors when they are available and keywords otherwise, which is the right answer almost always. Keyword forces text matching. Vector forces embeddings and fails loudly if they are unavailable, which is useful only when debugging.",
        ["auto", "lexical", "vector"]],
    ],
  },
  {
    title: "Scheduled searches",
    subtitle: "Run a search on its own, once a day.",
    blurb:
      "A scheduled search fetches and scores in the background so results are waiting when you next open the app. JobLookup has to be running at the time for it to fire; this is a timer inside the app, not a Windows scheduled task.",
    fields: [
      ["scheduler.enabled", "Run a search automatically", "boolean",
        "On runs one full search a day at the time below. Everything else about it is identical to pressing Run search yourself."],
      ["scheduler.hour", "Hour", "number",
        "0 to 23, in your local time. Early morning means fresh postings are waiting when you start the day."],
      ["scheduler.minute", "Minute", "number", "0 to 59."],
    ],
  },
];

// Which settings a person actually changes. Everything else lives in Advanced,
// which is the same controls again with nothing left out.
const BASIC_PATHS = [
  "search.recency_days",
  "search.max_jobs_per_source",
  "matching.prefilter_keep",
  "matching.rescore_existing",
  "matching.strong_threshold",
  "matching.good_threshold",
  "tailor.output_format",
  "tailor.style_guard",
  "scheduler.enabled",
  "scheduler.hour",
];

//: Survives the re-render that follows saving, so you stay where you were.
let activeTab = "basic";

export async function renderSettings(container, query) {
  // Settings values are a file read; probing every model provider is several
  // network calls. Only the first is awaited, so the screen appears at once.
  const payload = await api.settings();
  const wantsModel = query?.get("focus") === "model";

  const modelSlot = el("div", { class: "stack" }, modelPlaceholder());
  const budgetSlot = el("div", { class: "stack" }, budgetPlaceholder());
  const diagnosticsSlot = el("div", { class: "stack" }, diagnosticsPlaceholder());
  const tabSlot = el("div", { class: "stack" });

  const tabs = el("div", { class: "tab-bar", role: "tablist" },
    ...[
      ["basic", "Basic", "The handful of settings most people change."],
      ["advanced", "Advanced", "Every number the app uses to make a judgement."],
    ].map(([key, label, hint]) =>
      el("button", {
        class: `tab${activeTab === key ? " is-on" : ""}`,
        role: "tab",
        title: hint,
        "aria-selected": activeTab === key ? "true" : "false",
        onClick: () => {
          if (activeTab === key) return;
          activeTab = key;
          for (const button of tabs.children) {
            const on = button.dataset.tab === activeTab;
            button.classList.toggle("is-on", on);
            button.setAttribute("aria-selected", on ? "true" : "false");
          }
          showTab(tabSlot, payload, container);
        },
        "data-tab": key,
      }, label)
    )
  );

  mount(
    container,
    el("div", { class: "page-head" },
      el("h1", { text: "Settings" }),
      el("p", { text: "Your choices are written to config/local.yaml, which survives an update. API keys never go in there." })
    ),
    el("div", { class: "stack" },
      budgetSlot,
      modelSlot,
      tabs,
      tabSlot,
      diagnosticsSlot
    )
  );

  showTab(tabSlot, payload, container);

  // The two slow parts arrive on their own and fill themselves in.
  api.providers()
    .then(({ providers }) => {
      if (!container.isConnected) return;
      mount(modelSlot, modelCard({ ...payload, providers }, container));
      if (wantsModel) revealModel(modelSlot);
      const models = providers.find((entry) => entry.key === payload.settings.llm.provider)?.models || [];
      paintBudget(budgetSlot, payload, models, container);
    })
    .catch((error) => {
      if (!container.isConnected) return;
      mount(modelSlot, modelFailed(error.message));
      paintBudget(budgetSlot, payload, [], container);
    });

  api.health()
    .then((health) => {
      if (container.isConnected) mount(diagnosticsSlot, diagnosticsCard(health));
    })
    .catch(() => {});
}

function showTab(slot, payload, container) {
  if (activeTab === "basic") {
    mount(slot, basicCard(payload.settings, container));
    return;
  }
  mount(slot, ...TUNING.map((group) => tuningCard(group, payload.settings, container)), storageCard());
}

/** The model card before its provider probe has come back. */
function modelPlaceholder() {
  return card(
    {
      title: "Language model",
      subtitle: "Checking which providers are reachable...",
      actions: spinner(18),
      tone: "strong",
    },
    el("div", { class: "skeleton-stack" }, el("div", { class: "skeleton short" }), el("div", { class: "skeleton" }))
  );
}

function modelFailed(message) {
  return card(
    { title: "Language model", tone: "strong" },
    el("div", { class: "notice danger" },
      el("strong", { text: "Could not check the providers" }),
      el("div", { class: "small-text", text: message })
    )
  );
}

/** Diagnostics runs every health check, so it arrives after the page does. */
function diagnosticsPlaceholder() {
  return card(
    {
      title: "Diagnostics",
      subtitle: "Running every check the app can make about its own setup...",
      actions: spinner(18),
    },
    el("div", { class: "skeleton-stack" },
      el("div", { class: "skeleton short" }),
      el("div", { class: "skeleton short" })
    )
  );
}

function budgetPlaceholder() {
  return card(
    { title: "Model spending", subtitle: "Working out what a search costs...", actions: spinner(18) },
    el("div", { class: "skeleton-stack" }, el("div", { class: "skeleton" }))
  );
}

// --- what a search costs ------------------------------------------------------
// Token cost is decided by how much text is sent, not by which model reads it.
// The dial owns that, and shows the number moving as you drag it, because a
// trade-off you cannot see is a trade-off nobody makes deliberately.
function paintBudget(slot, payload, models, container) {
  const settings = payload.settings;
  const saved = settings.llm.economy ?? 50;
  let shown = saved;

  const auto = toggle(settings.llm.auto !== false, {
    label: "Choose the model and detail automatically",
    onChange: async (value) => {
      try {
        await api.saveSettings({ llm: { auto: value } });
        ok(value ? "Auto is on." : "Auto is off. Your own model settings are used as written.");
        await renderSettings(container);
      } catch (error) {
        auto.checked = !value;
        fail(error.message);
      }
    },
  });

  const slider = el("input", {
    type: "range",
    min: "0",
    max: "100",
    step: "5",
    value: String(saved),
    class: "depth-slider economy-slider",
    disabled: settings.llm.auto === false,
    "aria-label": "How much to spend per search",
  });

  const readout = el("div", { class: "budget-readout" });
  const detail = el("div", { class: "stack tight" });
  const save = el("button", {
    class: "ghost small",
    disabled: true,
    onClick: async () => {
      save.disabled = true;
      try {
        await api.saveSettings({ llm: { economy: Number(slider.value) } });
        ok("Saved.");
        await renderSettings(container);
      } catch (error) {
        fail(error.message);
        save.disabled = false;
      }
    },
  }, "Save this level");

  let timer;
  const refresh = async () => {
    shown = Number(slider.value);
    slider.style.setProperty("--fill", `${shown}%`);
    save.disabled = shown === saved || settings.llm.auto === false;
    try {
      const result = await api.budget({ economy: shown, models });
      if (slot.isConnected) mount(detail, budgetDetail(result, readout));
    } catch {
      /* The preview is a nicety; a failure here must not break Settings. */
    }
  };
  slider.addEventListener("input", () => {
    clearTimeout(timer);
    slider.style.setProperty("--fill", `${slider.value}%`);
    timer = setTimeout(refresh, 120);
  });
  refresh();

  mount(slot, card(
    {
      title: "Model spending",
      subtitle:
        "What one search costs is decided by how much text is sent to the model, not by which model reads it. This dial owns that. How many postings get sent at all is the depth slider on the Dashboard.",
      actions: el("span", { class: "chip", text: settings.llm.auto === false ? "manual" : "auto" }),
      tone: "strong",
    },
    splitRows(
      el("div", { class: "setting span-all" },
        el("div", { class: "setting-label" },
          el("span", { class: "setting-title", text: "Choose everything automatically" }),
          el("span", { class: "setting-help", text: "On picks the model, how much of each posting to send and how much the model writes back, from the one dial below. Off uses the model and reasoning settings you set yourself, exactly as written." })
        ),
        el("div", { class: "setting-control" }, auto)
      ),
      el("div", { class: "setting span-all" },
        el("div", { class: "setting-label" },
          el("span", { class: "setting-title", text: "How much to spend per search" }),
          el("span", { class: "setting-help", text: "Left spends as little as possible. Right spends whatever it takes. The estimate updates as you drag." })
        ),
        el("div", { class: "setting-control" }, el("div", { class: "depth-control" }, slider, readout))
      )
    ),
    detail,
    el("div", { class: "row" }, save)
  ));
}

function budgetDetail(result, readout) {
  const budget = result.budget || {};
  const estimate = result.estimate || {};
  const manual = result.manual_estimate || {};
  const saving = manual.total_tokens ? 1 - estimate.total_tokens / manual.total_tokens : 0;

  mount(readout,
    el("span", { class: "depth-name", text: budget.label || "" }),
    el("span", { class: "depth-detail",
      text: `about ${humanTokens(estimate.total_tokens)} tokens per search · ${estimate.calls} model calls · ${budget.model || "default model"}`,
    })
  );

  return el("div", { class: "stack tight" },
    el("p", { class: "card-sub", style: { margin: 0 }, text: budget.note || "" }),
    el("div", { class: "budget-facts" },
      fact("Model", `${budget.model || "provider default"}`, budget.tier_label || ""),
      fact("Each posting", `${budget.description_chars} characters`, "of its description is sent"),
      fact("Batch size", `${budget.score_batch_size} postings`, "judged in one call"),
      fact("Answers", `${budget.rationale_words} words`, "of reasoning per posting"),
      fact("Effort", budget.reasoning_effort || "model default", "how long it may think")
    ),
    saving > 0.02
      ? el("p", { class: "small-text muted", style: { margin: 0 },
          text: `That is about ${Math.round(saving * 100)}% fewer tokens than your saved manual settings would use.`,
        })
      : null,
    el("details", { class: "source-detail" },
      el("summary", { text: "Where the tokens go" }),
      el("div", { class: "detail-body" },
        el("div", { class: "budget-bars" },
          ...(result.breakdown || []).map((part) =>
            el("div", { class: "budget-bar" },
              el("div", { class: "budget-bar-head" },
                el("span", { text: part.label }),
                el("span", { class: "muted", text: `${humanTokens(part.tokens)} · ${Math.round(part.share * 100)}%` })
              ),
              el("div", { class: "budget-bar-track" },
                el("div", { class: "budget-bar-fill", style: { width: `${Math.max(1, part.share * 100)}%` } })
              ),
              el("div", { class: "field-help", text: part.note })
            )
          )
        ),
        el("p", { class: "small-text muted", text: "Estimated at about four characters per token. Good enough to compare settings; read your provider's dashboard for exact billing." })
      )
    )
  );
}

function fact(label, value, note) {
  return el("div", { class: "budget-fact" },
    el("span", { class: "budget-fact-label", text: label }),
    el("span", { class: "budget-fact-value", text: value }),
    note ? el("span", { class: "budget-fact-note", text: note }) : null
  );
}

/** Bring the model card into view and flash it, for arrivals from the status pill. */
function revealModel(slot) {
  const target = slot.firstElementChild;
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  target.classList.add("flash");
  setTimeout(() => target.classList.remove("flash"), 1600);
}

/** The everyday settings, pulled from the same definitions Advanced uses. */
function basicCard(settings, container) {
  const byPath = new Map();
  for (const group of TUNING) {
    for (const field of group.fields) byPath.set(field[0], field);
  }
  const fields = BASIC_PATHS.map((path) => byPath.get(path)).filter(Boolean);

  return tuningCard(
    {
      title: "Everyday settings",
      subtitle: "The ones worth knowing about. Advanced has these and everything else.",
      blurb:
        "Nothing is hidden from you here: Advanced is the same controls with the rest included. If you are not sure about a setting, the line under its name says what changing it does.",
      fields,
      flat: true,
    },
    settings,
    container
  );
}

// --- language model -----------------------------------------------------------
function currentChoice(settings) {
  const provider = settings.llm.provider;
  if (provider === "vscode" || provider === "copilot_cli") return `builtin:${provider}`;
  if (provider === "anthropic") return "preset:anthropic";
  return `preset:${settings.llm.openai_compat.preset || "custom"}`;
}

function shortLabel(preset) {
  return preset.label.replace(/\s*\(.*\)\s*$/, "");
}

function optionGroups(presets) {
  const free = presets.filter((preset) => !preset.needs_paid_key && preset.key !== "custom");
  const paid = presets.filter((preset) => preset.needs_paid_key);
  const other = presets.filter((preset) => preset.key === "custom");
  const asOption = (preset) => ({ value: `preset:${preset.key}`, label: shortLabel(preset) });

  return [
    ["GitHub Copilot - recommended", [
      { value: "builtin:vscode", label: "Through VS Code" },
      { value: "builtin:copilot_cli", label: "Through the Copilot CLI" },
    ]],
    ["Runs on this machine - free", free.map(asOption)],
    ["Hosted - needs a paid key", paid.map(asOption)],
    ["Anything else", other.map(asOption)],
  ].filter(([, items]) => items.length);
}

function modelCard(payload, container) {
  const settings = payload.settings;
  const presets = payload.presets || [];
  const active = (payload.providers || []).find((entry) => entry.key === settings.llm.provider) || {};
  const selected = currentChoice(settings);

  const select = el("select", {},
    ...optionGroups(presets).map(([label, items]) =>
      el("optgroup", { label },
        ...items.map((item) => el("option", { value: item.value, selected: item.value === selected }, item.label))
      )
    )
  );

  const detailSlot = el("div", { class: "stack tight" });
  let current = null;

  const paint = () => {
    current = buildDetail(select.value, settings, presets, payload);
    mount(
      detailSlot,
      current.note ? el("p", { class: "card-sub", style: { margin: 0 }, text: current.note }) : null,
      splitRows(...current.rows),
      current.keyNote ? el("div", { class: "notice info" }, el("p", { text: current.keyNote })) : null,
      select.value !== selected
        ? el("div", { class: "notice info" }, el("p", { text: "Press Apply to switch to this provider." }))
        : null
    );
  };
  select.addEventListener("change", paint);
  paint();

  const apply = el("button", {
    onClick: async () => {
      apply.disabled = true;
      try {
        const { provider, patch } = current.collect();
        await api.setProvider(provider);
        if (patch) await api.saveSettings(patch);
        ok("Language model updated.");
        await app.refreshState();
        await renderSettings(container);
      } catch (error) {
        fail(error.message);
      } finally {
        apply.disabled = false;
      }
    },
  }, "Apply");

  const test = el("button", {
    class: "ghost",
    onClick: async () => {
      test.disabled = true;
      test.textContent = "Testing...";
      try {
        const result = await api.testProvider();
        if (result.ok) ok(`The model answered: ${result.detail}`);
        else fail(`${result.detail}${result.fix ? ` - ${result.fix}` : ""}`);
      } catch (error) {
        fail(error.message);
      } finally {
        test.disabled = false;
        test.textContent = "Test the connection";
      }
    },
  }, "Test the connection");

  return card(
    {
      title: "Language model",
      subtitle:
        "One model answers at a time. The recommended route uses the GitHub Copilot seat you already have; nothing here ever requires a paid API key.",
      actions: el("span", {
        class: `chip ${active.available ? "matched" : "hard"}`,
        text: active.available ? active.active_model || "connected" : "not connected",
      }),
      tone: "strong",
    },
    activeStatus(active),
    field("Provider", select),
    detailSlot,
    el("div", { class: "row" }, apply, test)
  );
}

function activeStatus(status) {
  if (!status.label) return null;
  return el("div", { class: status.available ? "notice info" : "notice danger" },
    el("p", {}, el("strong", { text: `${status.label}: ` }), status.detail || ""),
    !status.available && status.setup_hint
      ? el("div", { class: "mono", style: { marginTop: "8px" }, text: status.setup_hint })
      : null
  );
}

function selectOf(options, value, labels = {}) {
  return el("select", {},
    ...options.map((option) =>
      el("option", { value: option, selected: String(value ?? "") === option }, labels[option] ?? (option || "default"))
    )
  );
}

/** A dropdown of `[value, label]` pairs that keeps an unlisted saved value. */
function labelledSelect(pairs, value) {
  const current = String(value ?? "");
  const options = pairs.some(([option]) => option === current) ? pairs : [...pairs, [current, current]];
  return el("select", {},
    ...options.map(([option, label]) =>
      el("option", { value: option, selected: option === current }, label)
    )
  );
}

function providerModels(payload, key) {
  return (payload.providers || []).find((entry) => entry.key === key)?.models || [];
}

/**
 * Pick a model by name from the list the provider actually reports.
 *
 * Falls back to a text box only when nothing can be listed, which for the VS
 * Code route means the bridge is not connected yet.
 */
function modelPicker(models, value, { autoLabel = "Automatic - let the provider choose" } = {}) {
  const known = [...new Set((models || []).filter(Boolean))];
  if (!known.length) {
    return el("input", { type: "text", value: value || "", placeholder: "model name" });
  }
  // A model saved earlier that the provider no longer lists still has to be
  // selectable, or opening this screen would silently change it.
  if (value && !known.includes(value)) known.unshift(value);
  return el("select", {},
    el("option", { value: "", selected: !value }, autoLabel),
    ...known.map((name) => el("option", { value: name, selected: name === value }, name))
  );
}

/** The fields that matter for one provider, and how to save them. */
function buildDetail(choice, settings, presets, payload) {
  const [kind, key] = choice.split(":");

  if (kind === "builtin" && key === "vscode") {
    const available = providerModels(payload, "vscode");
    const model = modelPicker(available, settings.llm.vscode.model || "");
    const effort = selectOf(EFFORTS, settings.llm.vscode.reasoning_effort || "", EFFORT_LABELS);
    const window = labelledSelect(CONTEXT_WINDOWS, settings.llm.vscode.context_window_tokens ?? "");
    return {
      note: "Goes through VS Code's Language Model API, the same route every Copilot-powered extension uses. Keep a VS Code window open while JobLookup is scoring.",
      rows: [
        settingRow(
          "Preferred model",
          model,
          available.length
            ? `Chosen from the ${available.length} model(s) your VS Code Copilot seat currently offers. Automatic picks a fast, inexpensive one. Larger models judge better and use more of your quota.`
            : "The bridge is not connected, so its model list cannot be read. Connect it and this becomes a dropdown; until then a name typed here is only checked on first use."
        ),
        settingRow(
          "Reasoning effort",
          effort,
          "How long the model may think before answering. Only some models accept it; the rest ignore it. Higher is slower and more accurate."
        ),
        settingRow(
          "Context window",
          window,
          "How much text may go into one call. Model default is right almost always. Reduce it only if you see 'context length exceeded' errors, and lower the scoring batch size too."
        ),
      ],
      collect: () => ({
        provider: { provider: "vscode", model: model.value.trim() },
        patch: {
          llm: {
            vscode: {
              reasoning_effort: effort.value || null,
              context_window_tokens: window.value ? Number(window.value) : null,
            },
          },
        },
      }),
    };
  }

  if (kind === "builtin") {
    // The CLI has no listing command, but it runs on the same Copilot seat, so
    // the bridge's list is the best available guess at valid names.
    const suggested = providerModels(payload, "vscode");
    const model = modelPicker(suggested, settings.llm.copilot_cli.model || "");
    const effort = selectOf(EFFORTS, settings.llm.copilot_cli.reasoning_effort || "", EFFORT_LABELS);
    const window = labelledSelect(
      [["default", "Default"], ["long_context", "Long context - more per call, slower"]],
      settings.llm.copilot_cli.context_window
    );
    const timeout = el("input", { type: "number", value: settings.llm.copilot_cli.request_timeout_s });
    return {
      note: "Works without VS Code, but it is slower and more quota-hungry: the CLI ships a large agent system prompt on every call. It also occasionally answers with a question instead of the work, which JobLookup detects and retries.",
      rows: [
        settingRow(
          "Preferred model",
          model,
          suggested.length
            ? "The CLI cannot list its own models, so these are the ones your VS Code seat reports. A name it does not accept fails on first use, not here."
            : "The CLI cannot list its models, so any name is accepted here and only fails on first use."
        ),
        settingRow("Reasoning effort", effort, "Higher is slower and more accurate. Not every model accepts it."),
        settingRow("Context window", window, "Long context fits more postings into one call at the cost of speed."),
        settingRow("Request timeout", timeout, "In seconds. Raise it, or lower the scoring batch size, if calls time out."),
      ],
      collect: () => ({
        provider: { provider: "copilot_cli", model: model.value.trim() },
        patch: {
          llm: {
            copilot_cli: {
              reasoning_effort: effort.value || null,
              context_window: window.value,
              request_timeout_s: Number(timeout.value) || 300,
            },
          },
        },
      }),
    };
  }

  const preset = presets.find((entry) => entry.key === key) || { key, label: key, suggested_models: [] };

  if (key === "anthropic") {
    const live = providerModels(payload, "anthropic");
    const model = modelPicker(
      live.length ? live : preset.suggested_models || [],
      settings.llm.anthropic.model || "",
      { autoLabel: "Automatic" }
    );
    const maxTokens = el("input", { type: "number", value: settings.llm.anthropic.max_tokens });
    return {
      note: preset.note,
      keyNote: `Set the key before starting JobLookup:  $env:${preset.api_key_env} = "<your key>"`,
      rows: [
        settingRow(
          "Model",
          model,
          live.length
            ? "Read live from your Anthropic account."
            : "Suggested names. The live list appears once a working key is set."
        ),
        settingRow(
          "Maximum reply tokens",
          maxTokens,
          "The longest answer the model may give. Too low truncates a scoring batch and wastes the call; 8192 comfortably fits the default batch of 12."
        ),
      ],
      collect: () => ({
        provider: { provider: "anthropic", preset: "anthropic", model: model.value.trim() },
        patch: { llm: { anthropic: { max_tokens: Number(maxTokens.value) || 8192 } } },
      }),
    };
  }

  const sameAsSaved = settings.llm.openai_compat.preset === key;
  const live = sameAsSaved ? providerModels(payload, "openai_compat") : [];
  const baseUrl = el("input", {
    type: "text",
    value: (sameAsSaved ? settings.llm.openai_compat.base_url : "") || preset.base_url || "",
    placeholder: preset.needs_base_url ? "https://..." : preset.base_url || "",
  });
  const model = modelPicker(
    live.length ? live : preset.suggested_models || [],
    (sameAsSaved ? settings.llm.openai_compat.model : "") || preset.suggested_models?.[0] || "",
    { autoLabel: "Automatic" }
  );
  const embed = el("input", {
    type: "text",
    value: (sameAsSaved ? settings.llm.openai_compat.embed_model : "") || preset.suggested_embed_models?.[0] || "",
    placeholder: "none - keyword recall stays in use",
  });

  const local = /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])/.test(preset.base_url || "");
  return {
    note: preset.note,
    keyNote: local
      ? "No key needed. Nothing leaves this machine."
      : `Set the key before starting JobLookup:  $env:${preset.api_key_env} = "<your key>"`,
    rows: [
      settingRow("Endpoint", baseUrl, preset.needs_base_url ? "Only you know this one." : "", { wide: true }),
      settingRow(
        "Model",
        model,
        live.length
          ? "Read live from the endpoint above. Save and reopen this screen after changing the endpoint to refresh it."
          : "Suggested names for this provider. The live list appears once the endpoint answers."
      ),
      settingRow("Embedding model", embed, "Optional. Setting one upgrades recall from keyword matching to vector similarity, which finds roles worded differently from your CV."),
    ],
    collect: () => ({
      provider: {
        provider: "openai_compat",
        preset: key,
        base_url: baseUrl.value.trim(),
        model: model.value.trim(),
        embed_model: embed.value.trim(),
      },
      patch: null,
    }),
  };
}

// --- tuning ------------------------------------------------------------------
const SELECT_LABELS = {
  docx: "Word document (.docx)",
  markdown: "Markdown (.md)",
  both: "Both",
  auto: "Automatic - vectors when available",
  lexical: "Keyword only",
  vector: "Embeddings only",
};

function tuningCard(group, settings, container) {
  const controls = group.fields.map(([path, label, kind, help, options]) => {
    const value = read(settings, path);
    let control;
    if (kind === "boolean") control = toggle(Boolean(value), { label });
    else if (kind === "select") control = selectOf(options, value, SELECT_LABELS);
    else if (kind === "number") control = el("input", { type: "number", step: "any", value: value ?? "" });
    else control = el("input", { type: "text", value: value ?? "" });
    return { path, kind, control, node: settingRow(label, control, help) };
  });

  const save = el("button", {
    class: "ghost",
    onClick: async () => {
      const patch = {};
      for (const entry of controls) {
        let value;
        if (entry.kind === "boolean") value = entry.control.checked;
        else if (entry.kind === "number") value = entry.control.value === "" ? null : Number(entry.control.value);
        else value = entry.control.value;
        if (value === null) continue;
        write(patch, entry.path, value);
      }
      try {
        await api.saveSettings(patch);
        ok(`${group.title} saved.`);
        await renderSettings(container);
      } catch (error) {
        fail(error.message);
      }
    },
  }, "Save changes");

  const body = [
    group.blurb ? el("p", { class: "section-blurb", text: group.blurb }) : null,
    splitRows(...controls.map((entry) => entry.node)),
    el("div", { class: "row" }, save),
  ];

  // Basic is one open card; Advanced is a stack of collapsed ones.
  return group.flat
    ? card({ title: group.title, subtitle: group.subtitle }, ...body)
    : accordion({ title: group.title, subtitle: group.subtitle }, ...body);
}
function read(object, path) {
  return path.split(".").reduce((node, key) => (node == null ? undefined : node[key]), object);
}

function write(object, path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  let node = object;
  for (const key of keys) node = node[key] ??= {};
  node[last] = value;
}

// --- diagnostics --------------------------------------------------------------
function diagnosticsCard(health) {
  const failures = (health.checks || []).filter((check) => check.status !== "ok").length;
  return accordion(
    {
      title: "Diagnostics",
      subtitle: "Every check the app can make about its own setup. Anything failing prints the command that fixes it.",
      badge: el("span", {
        class: `chip ${health.status === "ok" ? "matched" : health.status === "failed" ? "hard" : "learnable"}`,
        text: failures ? `${failures} to look at` : "all clear",
      }),
      open: health.status !== "ok",
    },
    splitRows(
      ...(health.checks || []).map((check) =>
        el("div", { class: "status-line" },
          el("span", { class: `status-dot ${check.status}` }),
          el("div", { class: "status-body" },
            el("strong", { text: check.label }),
            el("span", { class: "small-text muted", text: check.detail }),
            check.fix ? el("span", { class: "mono", text: check.fix }) : null
          )
        )
      )
    )
  );
}

function storageCard() {
  const body = el("div", { class: "skeleton-stack" },
    el("div", { class: "skeleton short" }),
    el("div", { class: "skeleton short" })
  );
  api.paths().then((paths) => {
    mount(body,
      el("div", { class: "rows split" },
        ...Object.entries(paths).map(([key, value]) =>
          el("div", { class: "status-line" },
            el("div", { class: "status-body" },
              el("strong", { text: key.replace(/_/g, " ") }),
              el("span", { class: "mono", text: value })
            )
          )
        )
      )
    );
  });
  return accordion(
    { title: "Where things are stored", subtitle: "Nothing here leaves this machine." },
    body
  );
}
