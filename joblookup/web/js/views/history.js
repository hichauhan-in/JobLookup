// Search history: every run, what it produced, and the means to forget it.
//
// The runs themselves were always recorded; what was missing was the link from
// a run to the postings it found, so history could only ever show statistics.
// Deleting a run forgets the run, never the postings, which usually belong to
// several runs and to your applications.

import { api } from "../api.js";
import { app } from "../app.js";
import { card, el, mount, openDialog } from "../dom.js";
import { plural, relativeDate } from "../format.js";
import { fail, ok } from "../notify.js";

export async function renderHistory(container) {
  const payload = await api.history();
  const runs = payload.runs || [];

  const clearButton = el("button", {
    class: "ghost small danger",
    disabled: !runs.length,
    onClick: async () => {
      if (!confirm(`Forget all ${runs.length} search(es)? Your postings, scores and applications are not touched.`)) return;
      try {
        const result = await api.clearHistory();
        ok(`Forgot ${plural(result.removed || 0, "search", "es")}.`);
        await renderHistory(container);
      } catch (error) {
        fail(error.message);
      }
    },
  }, "Clear all history");

  mount(
    container,
    el("div", { class: "page-head" },
      el("div", { class: "row between" },
        el("div", {},
          el("h1", { text: "Search history" }),
          el("p", { text: "Every search you have run and what it found. Open one to see its results." })
        ),
        clearButton
      )
    ),
    el("div", { class: "stack" },
      runs.length
        ? card({ title: `${plural(runs.length, "search", "es")} recorded` }, historyTable(runs, container))
        : card(
            { title: "Nothing here yet" },
            el("p", { class: "muted", text: "Run a search from the dashboard and it will appear here with its results." }),
            el("div", { class: "row" },
              el("button", { class: "ghost small", onClick: () => app.go("/dashboard") }, "Go to the dashboard")
            )
          )
    )
  );
}

function historyTable(runs, container) {
  return el("table", {},
    el("thead", {}, el("tr", {},
      el("th", { text: "When" }),
      el("th", { text: "Status" }),
      el("th", { text: "Found" }),
      el("th", { text: "New" }),
      el("th", { text: "Sources" }),
      el("th", { text: "" })
    )),
    el("tbody", {},
      ...runs.map((run) => el("tr", {},
        el("td", { title: exactTime(run.started_at) }, relativeDate(asIso(run.started_at))),
        el("td", {}, el("span", { class: `chip ${statusTone(run.status)}`, text: run.status })),
        el("td", { text: String(run.result_count ?? 0) }),
        el("td", { text: String(run.new_count ?? 0) }),
        el("td", { class: "muted", text: (run.sources || []).join(", ") || "none" }),
        el("td", {},
          el("div", { class: "row tight" },
            el("button", {
              class: "ghost small",
              disabled: !run.result_count,
              onClick: () => showResults(run),
            }, "Results"),
            el("button", {
              class: "ghost small danger",
              onClick: () => forget(run, container),
            }, "Delete")
          )
        )
      ))
    )
  );
}

function statusTone(status) {
  if (status === "ok") return "matched";
  if (status === "failed") return "hard";
  if (status === "running") return "";
  return "learnable";
}

async function forget(run, container) {
  if (!confirm("Forget this search? The postings it found stay in your database.")) return;
  try {
    await api.deleteHistoryRun(run.id);
    ok("Search forgotten.");
    await renderHistory(container);
  } catch (error) {
    fail(error.message);
  }
}

async function showResults(run) {
  let payload;
  try {
    payload = await api.historyRun(run.id);
  } catch (error) {
    fail(error.message);
    return;
  }
  const results = payload.results || [];
  const stats = run.stats || {};
  const total = run.result_count ?? results.length;
  const shown = results.length < total ? `Showing the top ${results.length} of ${total}` : `${plural(total, "posting")}`;

  openDialog(
    {
      title: `Search from ${exactTime(run.started_at)}`,
      subtitle:
        `${shown}, ${run.new_count ?? 0} of them new to your database. ` +
        `${stats.fetched ?? 0} fetched, ${stats.duplicates ?? 0} merged as duplicates, ` +
        `${stats.too_old ?? 0} too old to keep.`,
    },
    results.length
      ? el("table", {},
          el("thead", {}, el("tr", {},
            el("th", { text: "Role" }),
            el("th", { text: "Company" }),
            el("th", { text: "Where" }),
            el("th", { text: "Band" })
          )),
          el("tbody", {},
            ...results.map((job) => el("tr", {},
              el("td", {},
                el("a", { href: `#/job/${job.id}` }, job.title || "Untitled"),
                job.is_new ? el("span", { class: "chip", style: { marginLeft: "8px" }, text: "new" }) : null
              ),
              el("td", { text: job.company || "" }),
              el("td", { class: "muted", text: job.location || job.work_mode || "" }),
              el("td", {}, job.band ? el("span", { class: `chip ${job.band}`, text: job.band }) : el("span", { class: "muted", text: "not scored" }))
            ))
          )
        )
      : el("p", { class: "muted", text: "This search produced no postings." })
  );
}

/** SQLite writes "YYYY-MM-DD HH:MM:SS" in UTC with no marker of either fact. */
function asIso(stamp) {
  return stamp ? `${String(stamp).replace(" ", "T")}Z` : null;
}

/** A search happened at a moment; "just posted" is language for a job, not a run. */
function exactTime(stamp) {
  const iso = asIso(stamp);
  if (!iso) return "an unknown time";
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? "an unknown time" : when.toLocaleString();
}
