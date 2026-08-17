// The dashboard: what to do next, what is in the database, and the button that
// starts a search.

import { api } from "../api.js";
import { app } from "../app.js";
import { card, chipGroup, el, mount, toggle } from "../dom.js";
import { plural, relativeDate } from "../format.js";
import { fail, ok, warn } from "../notify.js";
import { TaskView, watch } from "../tasks.js";

// The two dials worth reaching for mid-search, in words rather than numbers.
const WINDOWS = [
  [1, "24 hours", "Only today's postings. Fastest, and everything is fresh."],
  [3, "3 days", "A good daily rhythm."],
  [7, "1 week", "The default. Most postings are still open."],
  [14, "2 weeks", "Wider net, some will already be filled."],
  [30, "1 month", "Everything still listed. Expect stale results."],
];

// Depth is a slider because it is a continuum, not a set of categories. Each
// stop names what it costs, since that is the part people care about.
const DEPTHS = [
  { keep: 20, label: "Glance", calls: 2 },
  { keep: 40, label: "Quick", calls: 4 },
  { keep: 80, label: "Light", calls: 7 },
  { keep: 120, label: "Balanced", calls: 10 },
  { keep: 200, label: "Wide", calls: 17 },
  { keep: 300, label: "Thorough", calls: 25 },
  { keep: 450, label: "Deep", calls: 38 },
  { keep: 600, label: "Exhaustive", calls: 50 },
];

export async function renderDashboard(container) {
  const [state, runsPayload, settingsPayload] = await Promise.all([
    app.refreshState(),
    api.runs(),
    api.settings(),
  ]);
  const counts = state.counts || {};
  const steps = state.onboarding || {};
  const runs = runsPayload.runs || [];
  const settings = settingsPayload.settings || {};

  const taskSlot = el("div", { class: "stack tight" });
  const tweaks = searchControls(settings);

  const searchButton = el("button", { onClick: () => runSearch(taskSlot, searchButton, container, tweaks) }, "Run search");
  const matchButton = el("button", { class: "ghost", onClick: () => runMatch(taskSlot, matchButton, container) }, "Score again");

  mount(
    container,
    el("div", { class: "page-head" },
      el("h1", { text: "Dashboard" }),
      el("p", { text: "Search your sources, then read what came back. Nothing is sent anywhere except the model you chose and the job boards themselves." })
    ),

    el("div", { class: "stack" },
      setupCard(steps),

      el("div", { class: "grid four" },
        stat(counts.jobs, "postings stored"),
        stat(counts.strong, "strong"),
        stat(counts.good, "good"),
        stat(counts.stretch, "stretch")
      ),

      card(
        {
          title: "Search every enabled source",
          subtitle: `${plural(counts.sources_enabled || 0, "source")} enabled. Results are deduplicated, then scored against your profile.`,
          actions: el("div", { class: "row tight" }, matchButton, searchButton),
        },
        tweaks.node,
        taskSlot
      ),

      runs.length ? card({ title: "Recent runs" }, runsTable(runs)) : null
    )
  );
}

/**
 * The handful of knobs worth having at the moment of searching.
 *
 * Everything here also lives in Settings. The point is that changing your mind
 * about how far back to look should not be a trip to another screen, and a
 * one-off change should not quietly become permanent.
 */
function searchControls(settings) {
  const savedWindow = settings.search?.recency_days ?? 7;
  const savedDepth = settings.matching?.prefilter_keep ?? 120;
  const savedRemote = Boolean(settings.search?.remote_only);

  const window = chipGroup(WINDOWS, nearest(WINDOWS.map((w) => w[0]), savedWindow));
  const depth = depthSlider(savedDepth);
  const remote = toggle(savedRemote, { label: "Remote roles only" });
  const remember = toggle(false, { label: "Remember these as my defaults" });

  const node = el("div", { class: "search-controls" },
    dial("How far back to look", window, "Postings older than this are not fetched at all."),
    dial("How deep to search", depth.node, "How many postings reach the model, which is what a search costs you."),
    dial("Remote only", remote, "Drops anything not positively identified as a remote role."),
    dial("Keep these", remember, "On writes these three to Settings. Off applies them to this search only.")
  );

  return {
    node,
    read: () => ({
      recency_days: Number(window.value),
      prefilter_keep: depth.value(),
      remote_only: remote.checked,
      remember: remember.checked,
      then_match: true,
    }),
  };
}

/**
 * Depth as a slider with named stops.
 *
 * The underlying number is "postings that reach the model", which is meaningless
 * on its own, so each stop shows the name, the count and the rough model-call
 * cost. That last figure is the one that decides whether a search is worth it.
 */
function depthSlider(saved) {
  const index = DEPTHS.reduce(
    (best, step, at) => (Math.abs(step.keep - saved) < Math.abs(DEPTHS[best].keep - saved) ? at : best),
    0
  );

  const input = el("input", {
    type: "range",
    min: "0",
    max: String(DEPTHS.length - 1),
    step: "1",
    value: String(index),
    class: "depth-slider",
    "aria-label": "How deep to search",
  });
  const readout = el("div", { class: "depth-readout" });

  const paint = () => {
    const at = Number(input.value);
    const step = DEPTHS[at];
    // The track's filled portion is drawn from this, so it reaches the very end
    // at the top of the range instead of stopping at the thumb's centre.
    input.style.setProperty("--fill", `${(at / (DEPTHS.length - 1)) * 100}%`);
    mount(readout,
      el("span", { class: "depth-name", text: step.label }),
      el("span", { class: "depth-detail", text: `${step.keep} postings scored · about ${step.calls} model calls` })
    );
    input.title = `${step.label}: ${step.keep} postings`;
  };
  input.addEventListener("input", paint);
  paint();

  return {
    node: el("div", { class: "depth-control" }, input, readout),
    value: () => DEPTHS[Number(input.value)].keep,
  };
}

function dial(label, control, help) {
  return el("div", { class: "search-dial" },
    el("div", { class: "dial-label" },
      el("span", { class: "dial-title", text: label }),
      el("span", { class: "dial-help", text: help })
    ),
    el("div", { class: "dial-control" }, control)
  );
}

/** Snap a saved number onto the nearest offered choice, so nothing looks unselected. */
function nearest(options, value) {
  return options.reduce((best, option) =>
    Math.abs(option - value) < Math.abs(best - value) ? option : best, options[0]);
}

function stat(value, label) {
  return el("div", { class: "stat" },
    el("div", { class: "value", text: String(value ?? 0) }),
    el("div", { class: "label", text: label })
  );
}

function setupCard(steps) {
  const items = [
    { done: steps.has_cv, title: "Upload your CVs", body: "Every version you have. They are merged into one profile.", route: "/profile" },
    { done: steps.has_targets, title: "Say what you are looking for", body: "Target titles, locations and work modes.", route: "/profile" },
    { done: steps.has_sources, title: "Choose your sources", body: "The keyless feeds work immediately. Company boards are where the best postings are.", route: "/sources" },
    { done: steps.has_jobs, title: "Run a search", body: "Press Run search below.", route: "/dashboard" },
    { done: steps.has_scores, title: "Read your matches", body: "Ranked by fit, with the reasoning shown.", route: "/matches" },
  ];
  const remaining = items.filter((item) => !item.done).length;
  if (!remaining) return null;

  return card(
    {
      title: "Getting set up",
      subtitle: "Five things once, then it is one button from here on.",
      actions: el("span", { class: "chip", text: `${remaining} left` }),
    },
    el("div", { class: "steps" },
      ...items.map((item) =>
        el("div", { class: `step ${item.done ? "done" : ""}` },
          el("div", { class: "mark", text: item.done ? "✓" : "" }),
          el("div", { class: "body" },
            el("b", { text: item.title }),
            el("span", { class: "muted small-text", text: item.body })
          ),
          item.done ? null : el("button", { class: "ghost small", onClick: () => app.go(item.route) }, "Go")
        )
      )
    )
  );
}

function runsTable(runs) {
  return el("table", {},
    el("thead", {}, el("tr", {},
      el("th", { text: "Started" }), el("th", { text: "Status" }),
      el("th", { text: "New" }), el("th", { text: "Duplicates" }), el("th", { text: "Sources" })
    )),
    el("tbody", {},
      ...runs.slice(0, 8).map((run) => {
        const stats = run.stats || {};
        return el("tr", {},
          el("td", { text: relativeDate(run.started_at?.replace(" ", "T") + "Z") }),
          el("td", { text: run.status }),
          el("td", { text: String(stats.new ?? 0) }),
          el("td", { text: String(stats.duplicates ?? 0) }),
          el("td", { class: "muted", text: (run.sources || []).join(", ") || "—" })
        );
      })
    )
  );
}

async function runSearch(slot, button, container, tweaks) {
  button.disabled = true;
  try {
    const options = tweaks.read();
    const { task } = await api.search(options);
    const view = new TaskView(task);
    mount(slot, view.node);
    const result = await watch(task, { view });
    const crawled = result.crawl || {};
    const matched = result.match || {};
    ok(`${crawled.new ?? 0} new posting(s), ${matched.scored ?? 0} scored.`);
    if (options.remember) ok("Saved as your defaults.");
    if (matched.skipped) warn(matched.skipped);
    await renderDashboard(container);
  } catch (error) {
    fail(error.message);
  } finally {
    button.disabled = false;
  }
}

async function runMatch(slot, button, container) {
  button.disabled = true;
  try {
    const { task } = await api.match(true);
    const view = new TaskView(task);
    mount(slot, view.node);
    const result = await watch(task, { view });
    ok(`${result.scored ?? 0} posting(s) scored using ${result.model_calls ?? 0} model call(s).`);
    await renderDashboard(container);
  } catch (error) {
    fail(error.message);
  } finally {
    button.disabled = false;
  }
}
