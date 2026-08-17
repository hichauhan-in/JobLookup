// One posting in full: why it scored what it did, where it was found, what to
// do about it, and the tailoring workflow.

import { api } from "../api.js";
import { app } from "../app.js";
import { card, el, field, mount, rows } from "../dom.js";
import { bandLabel, markdown, percent, relativeDate, salary, workMode } from "../format.js";
import { fail, ok, warn } from "../notify.js";
import { TaskView, watch } from "../tasks.js";

const STATUSES = ["saved", "applied", "interviewing", "offer", "rejected"];

export async function renderJob(container, jobId) {
  const payload = await api.job(jobId);
  const job = payload.job;
  const cvs = payload.cvs || [];
  const tailorSlot = el("div", { class: "stack" });

  if (payload.tailored?.markdown) {
    tailorSlot.append(tailoredCard(job, payload.tailored, payload.tailored.cv_id));
  }

  mount(
    container,
    el("div", { class: "page-head" },
      el("button", { class: "link small", onClick: () => history.back() }, "← Back"),
      el("div", { class: "row between", style: { marginTop: "8px" } },
        el("div", {},
          el("h1", { text: job.title }),
          el("p", { text: [job.company, job.location, workMode(job.work_mode), salary(job), relativeDate(job.posted_at)].filter(Boolean).join(" · ") })
        ),
        el("span", { class: `band band-${job.band || "rejected"}`, text: bandLabel(job.band) })
      )
    ),

    el("div", { class: "grid two" },
      el("div", { class: "stack" },
        scoreCard(job),
        gapsCard(job),
        card({ title: "Description" },
          el("div", { class: "description", text: job.description || "This source did not publish a description. Open the posting to read it." })
        )
      ),
      el("div", { class: "stack" },
        actionsCard(job),
        sourcesCard(job),
        tailorCard(job, cvs, tailorSlot),
        tailorSlot
      )
    )
  );
}

function scoreCard(job) {
  if (job.composite === null || job.composite === undefined) {
    return card({ title: "Fit" },
      el("p", { class: "muted", style: { margin: 0 }, text: "This posting has not been scored yet. Run matching from the dashboard." })
    );
  }
  return card(
    { title: "Fit", actions: el("span", { class: "chip", text: percent(job.composite) }) },
    el("div", { class: "stack tight" },
      fitBar("Already done it", job.direct_fit, "direct"),
      fitBar("Transfers across", job.transferable_fit, "transferable"),
      fitBar("Realistic step up", job.growth_fit, "growth")
    ),
    el("p", { style: { margin: 0 }, text: job.rationale || "No reasoning was recorded." }),
    job.blocker
      ? el("div", { class: "notice danger" }, el("p", {}, el("strong", { text: "Hard blocker: " }), job.blocker))
      : null
  );
}

function fitBar(label, value, kind) {
  return el("div", { class: "fit" },
    el("span", { class: "muted", text: label }),
    el("div", { class: "track" }, el("div", { class: `fill ${kind}`, style: { width: percent(value) } })),
    el("span", { class: "small-text", text: percent(value) })
  );
}

function gapsCard(job) {
  const matched = job.matched_skills || [];
  const learnable = job.learnable_gaps || [];
  const hard = job.hard_gaps || [];
  if (!matched.length && !learnable.length && !hard.length) return null;

  return card({ title: "Skills" },
    matched.length
      ? el("div", {}, el("h3", { text: "What you already have" }),
          el("div", { class: "chips" }, ...matched.map((item) => el("span", { class: "chip matched", text: item }))))
      : null,
    learnable.length
      ? el("div", {}, el("h3", { text: "Closeable in about a week" }),
          el("div", { class: "chips" }, ...learnable.map((item) => el("span", { class: "chip learnable", text: item }))))
      : null,
    hard.length
      ? el("div", {}, el("h3", { text: "Needs years, not days" }),
          el("div", { class: "chips" }, ...hard.map((item) => el("span", { class: "chip hard", text: item }))))
      : null
  );
}

function actionsCard(job) {
  const select = el("select", {},
    el("option", { value: "" }, "Not tracked"),
    ...STATUSES.map((status) => el("option", { value: status, selected: job.application_status === status }, status))
  );
  const notes = el("textarea", { placeholder: "Notes for yourself", value: job.application_notes || "" });

  select.addEventListener("change", async () => {
    if (!select.value) return;
    try {
      await api.setApplication(job.id, select.value, notes.value);
      ok(`Marked as ${select.value}.`);
      app.refreshState();
    } catch (error) {
      fail(error.message);
    }
  });

  return card({ title: "Track it" },
    el("div", { class: "row" },
      el("a", { class: "btn", href: job.apply_url || job.url, target: "_blank", rel: "noopener noreferrer" }, "Open the posting"),
      el("button", {
        class: "ghost",
        onClick: async () => {
          await api.hideJob(job.id, true);
          ok("Hidden from your matches.");
          app.go("/matches");
        },
      }, "Not interested")
    ),
    field("Status", select),
    field("Notes", notes),
    el("div", { class: "row" },
      el("button", {
        class: "ghost",
        onClick: async () => {
          try {
            await api.setApplication(job.id, select.value || "saved", notes.value);
            ok("Saved.");
          } catch (error) {
            fail(error.message);
          }
        },
      }, "Save notes")
    )
  );
}

function sourcesCard(job) {
  const sources = job.sources || [];
  if (!sources.length) return null;
  return card(
    {
      title: sources.length === 1 ? "Found on one source" : `Found on ${sources.length} sources`,
      subtitle:
        sources.length > 1
          ? "The same role, collapsed into one card. Any of these links reaches the same employer."
          : "",
    },
    rows(
      ...sources.map((source) =>
        el("div", { class: "status-line" },
          el("div", { class: "status-body" }, el("strong", { text: source.source_key })),
          source.url
            ? el("a", { class: "small-text", href: source.url, target: "_blank", rel: "noopener noreferrer" }, "Open")
            : el("span", { class: "muted small-text", text: "no link" })
        )
      )
    )
  );
}

function tailorCard(job, cvs, slot) {
  if (!cvs.length) {
    return card(
      { title: "Tailor your CV", subtitle: "Upload a CV first and this rewrites it for this specific posting." },
      el("div", { class: "row" }, el("button", { class: "ghost", onClick: () => app.go("/profile") }, "Upload a CV"))
    );
  }

  const select = el("select", {},
    ...cvs.map((cv) => el("option", { value: cv.id, selected: Boolean(cv.is_primary) }, cv.label))
  );
  const button = el("button", { onClick: () => run() }, "Tailor for this job");

  async function run() {
    button.disabled = true;
    try {
      const { task } = await api.tailor(job.id, Number(select.value));
      const view = new TaskView(task);
      mount(slot, view.node);
      const result = await watch(task, { view });
      if (result.moved_to_upskilling?.length) {
        warn(`Moved to upskilling because your CV does not evidence them: ${result.moved_to_upskilling.join(", ")}`);
      }
      mount(slot, tailoredCard(job, result, Number(select.value)));
      ok("Tailored CV ready.");
    } catch (error) {
      fail(error.message);
    } finally {
      button.disabled = false;
    }
  }

  return card(
    {
      title: "Tailor your CV",
      subtitle: "Rewrites your CV for this posting using only what it already contains. Anything you cannot honestly claim goes on the prep sheet instead.",
    },
    field("Base it on", select),
    el("div", { class: "row" }, button)
  );
}

function tailoredCard(job, result, cvId) {
  const base = `/api/jobs/${job.id}/tailor/download?cv_id=${cvId}`;
  return card(
    {
      title: "Tailored CV",
      subtitle: result.style_report?.changes
        ? `Style guard rewrote ${result.style_report.changes} passage(s).${result.style_report.flagged?.length ? ` Flagged: ${result.style_report.flagged.join(", ")}.` : ""}`
        : "",
    },
    el("div", { class: "row" },
      result.docx_path ? el("a", { class: "btn", href: `${base}&kind=docx` }, "Download .docx") : null,
      el("a", { class: "btn ghost", href: `${base}&kind=markdown` }, "Download Markdown"),
      el("a", { class: "btn ghost", href: `${base}&kind=prep` }, "Interview prep")
    ),
    el("details", {}, el("summary", { text: "Preview the CV" }), el("div", { html: markdown(result.markdown || "") })),
    result.prep_markdown
      ? el("details", {}, el("summary", { text: "Preview the interview prep sheet" }), el("div", { html: markdown(result.prep_markdown) }))
      : null
  );
}
