// The matches list: filter, scan, open.

import { api } from "../api.js";
import { app } from "../app.js";
import { card, chipToggle, el, mount, settingRow, spinner, toggle } from "../dom.js";
import { bandLabel, percent, relativeDate, salary, truncate, workMode } from "../format.js";
import { fail } from "../notify.js";

const BANDS = ["strong", "good", "stretch", "rejected"];
const MODES = ["remote", "hybrid", "onsite"];

const filter = {
  bands: ["strong", "good", "stretch"],
  work_modes: [],
  max_age_days: null,
  query: "",
  include_hidden: false,
  scored_only: true,
  //: Which search to show. "latest" is resolved server-side so it stays right
  //: after a new search finishes; "all" is everything ever collected.
  run: "latest",
  run_id: null,
  limit: 100,
  offset: 0,
};

export async function renderMatches(container) {
  const results = el("div", { class: "cards-grid" });
  const runSlot = el("div", { style: { flex: "1 1 240px" } });

  const search = el("input", {
    type: "search",
    placeholder: "Filter by title or company",
    value: filter.query,
  });
  let debounce;
  search.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      filter.query = search.value;
      load(results);
    }, 250);
  });

  const age = el("select", {},
    ...[["", "Any age"], ["1", "Today"], ["3", "3 days"], ["7", "7 days"], ["14", "14 days"], ["30", "30 days"]]
      .map(([value, label]) => el("option", { value, selected: String(filter.max_age_days ?? "") === value }, label))
  );
  age.addEventListener("change", () => {
    filter.max_age_days = age.value ? Number(age.value) : null;
    load(results);
  });

  const unscored = toggle(!filter.scored_only, {
    label: "Include unscored postings",
    onChange: (value) => {
      filter.scored_only = !value;
      load(results);
    },
  });

  mount(
    container,
    el("div", { class: "page-head" },
      el("h1", { text: "Matches" }),
      el("p", { text: "Your most recent search, ranked by fit rather than by keyword. Stretch means the gap is real but closeable, and those are usually the interesting ones." })
    ),
    el("div", { class: "stack" },
      card({ title: "Filters" },
        el("div", { class: "row" },
          el("div", { style: { flex: "1 1 260px" } }, search),
          el("div", { style: { flex: "0 0 150px" } }, age),
          runSlot
        ),
        chipGroup("Band", BANDS, bandLabel, filter.bands, results),
        chipGroup("Work mode", MODES, workMode, filter.work_modes, results),
        settingRow(
          "Include unscored postings",
          unscored,
          "Everything collected but not yet judged against your profile."
        )
      ),
      results
    )
  );

  await load(results, runSlot);
}

/** The run picker, rebuilt from whatever the last query reported. */
function paintRunPicker(slot, payload, results) {
  const runs = payload.runs || [];
  const withResults = runs.filter((run) => run.result_count > 0);
  if (!withResults.length) {
    mount(slot);
    return;
  }

  const options = [
    ["latest", "Latest search"],
    ["all", "Everything collected"],
    ...withResults.slice(0, 20).map((run) => [
      String(run.id),
      `${when(run.started_at)} - ${run.result_count} found`,
    ]),
  ];

  const chosen = filter.run === "latest" || filter.run === "all" ? filter.run : String(filter.run_id);
  const select = el("select", {},
    ...options.map(([value, label]) =>
      el("option", { value, selected: value === chosen }, label)
    )
  );
  select.addEventListener("change", () => {
    if (select.value === "latest" || select.value === "all") {
      filter.run = select.value;
      filter.run_id = null;
    } else {
      filter.run = "one";
      filter.run_id = Number(select.value);
    }
    load(results, slot);
  });

  mount(slot, select);
}

function when(stamp) {
  const iso = stamp ? `${String(stamp).replace(" ", "T")}Z` : null;
  const date = iso ? new Date(iso) : null;
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "unknown time";
}

function chipGroup(title, values, labelOf, collection, results) {
  return el("div", { class: "field" },
    el("label", { text: title }),
    el("div", { class: "row tight" },
      ...values.map((value) =>
        chipToggle(labelOf(value), collection.includes(value), (on) => {
          const index = collection.indexOf(value);
          if (on && index === -1) collection.push(value);
          if (!on && index !== -1) collection.splice(index, 1);
          load(results);
        })
      )
    )
  );
}

async function load(results, runSlot) {
  // Cards in the same grid the results will use, so the layout does not jump.
  mount(results,
    el("div", { class: "loading-head span-all" }, spinner(), el("span", { text: "Loading matches" })),
    ...Array.from({ length: 6 }, () => el("div", { class: "skeleton", style: { height: "150px" } }))
  );
  try {
    const payload = await api.queryJobs(filter);
    if (runSlot) paintRunPicker(runSlot, payload, results);
    const jobs = payload.jobs || [];
    if (!jobs.length) {
      mount(results, emptyState());
      return;
    }
    const scope =
      filter.run === "all"
        ? "across everything collected"
        : payload.run_id
          ? "from that search"
          : "across everything collected";
    mount(results,
      el("div", { class: "muted small-text span-all", text: `${jobs.length} shown ${scope}` }),
      ...jobs.map(jobCard)
    );
  } catch (error) {
    fail(error.message);
    mount(results, el("div", { class: "notice danger span-all", text: error.message }));
  }
}

function emptyState() {
  const scoped = filter.run !== "all";
  return el("div", { class: "empty span-all" },
    el("p", { text: scoped ? "Nothing in this search matches those filters." : "Nothing matches those filters." }),
    el("p", { class: "small-text", text: scoped
      ? "Widen the bands, or switch the search selector to Everything collected to look across all your runs."
      : "Widen the bands, extend the age window, or run a search from the dashboard." }),
    el("button", { class: "ghost", onClick: () => app.go("/dashboard") }, "Go to dashboard")
  );
}

function jobCard(job) {
  const money = salary(job);
  const meta = [
    job.company,
    job.location || "Location not stated",
    workMode(job.work_mode),
    money,
    relativeDate(job.posted_at),
    job.source_count > 1 ? `${job.source_count} sources` : null,
  ].filter(Boolean);

  const gaps = [
    ...(job.matched_skills || []).slice(0, 4).map((item) => el("span", { class: "chip matched", text: item })),
    ...(job.learnable_gaps || []).slice(0, 3).map((item) => el("span", { class: "chip learnable", text: `${item} · learnable` })),
    ...(job.hard_gaps || []).slice(0, 2).map((item) => el("span", { class: "chip hard", text: item })),
  ];

  return el("article", {
      class: `job-card band-${job.band || "rejected"}`,
      onClick: () => app.go(`/job/${job.id}`),
    },
    el("div", { class: "row between" },
      el("div", {},
        el("h3", { text: job.title }),
        el("div", { class: "job-meta" }, ...meta.map((item) => el("span", { text: item })))
      ),
      el("div", { class: "row" },
        job.application_status ? el("span", { class: "chip", text: job.application_status }) : null,
        el("span", { class: `band band-${job.band || "rejected"}`, text: bandLabel(job.band) }),
        job.composite !== undefined && job.composite !== null
          ? el("span", { class: "muted small-text", text: percent(job.composite) })
          : null
      )
    ),
    job.rationale ? el("p", { class: "small-text", style: { margin: "8px 0 0" }, text: truncate(job.rationale, 220) }) : null,
    gaps.length ? el("div", { class: "chips", style: { marginTop: "9px" } }, ...gaps) : null
  );
}
