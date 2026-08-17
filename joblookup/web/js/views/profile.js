// The profile: the CVs it was built from, the answers only you can give, and
// what the merge produced.

import { api } from "../api.js";
import { app } from "../app.js";
import { card, chipToggle, el, field, listInput, mount, readList, rows, spinner, splitRows } from "../dom.js";
import { plural } from "../format.js";
import { fail, ok } from "../notify.js";
import { TaskView, watch } from "../tasks.js";

const WORK_MODES = ["remote", "hybrid", "onsite"];

export async function renderProfile(container) {
  const [{ cvs }, { profile }] = await Promise.all([api.cvs(), api.profile()]);
  const data = profile.data || {};
  const taskSlot = el("div", { class: "stack tight" });

  mount(
    container,
    el("div", { class: "page-head" },
      el("h1", { text: "Profile" }),
      el("p", { text: "Upload every version of your CV you have. A skill mentioned in more of them counts for more, and each file stays available as a base for tailoring." })
    ),
    el("div", { class: "grid two" },
      el("div", { class: "stack" }, cvCard(cvs, taskSlot, container), taskSlot, skillsCard(data)),
      el("div", { class: "stack" }, preferencesCard(data, container), extractedCard(data))
    )
  );
}

// --- CVs ---------------------------------------------------------------------
function cvCard(cvs, taskSlot, container) {
  const input = el("input", { type: "file", accept: ".pdf,.docx,.txt,.md,.rtf", multiple: true });
  const label = el("input", { type: "text", placeholder: "Optional label, e.g. 'SRE version'" });
  const button = el("button", { onClick: upload }, "Upload");

  async function upload() {
    const files = [...(input.files || [])];
    if (!files.length) {
      fail("Choose a file first.");
      return;
    }
    button.disabled = true;
    try {
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        if (label.value.trim()) form.append("label", label.value.trim());
        const response = await api.upload("/api/cvs", form);
        const view = new TaskView(response.task);
        taskSlot.append(view.node);
        await watch(response.task, { view });
      }
      ok(`${plural(files.length, "CV")} read and merged.`);
      await renderProfile(container);
    } catch (error) {
      fail(error.message);
    } finally {
      button.disabled = false;
    }
  }

  return card(
    {
      title: "Your CVs",
      subtitle: "PDF, DOCX, Markdown or plain text. A scanned PDF has no text to read.",
      actions: cvs.length ? el("span", { class: "chip", text: plural(cvs.length, "file") }) : null,
    },
    el("div", { class: "row" },
      el("div", { style: { flex: "1 1 220px" } }, input),
      el("div", { style: { flex: "1 1 180px" } }, label),
      button
    ),
    cvs.length ? splitRows(...cvs.map((cv) => cvRow(cv, taskSlot, container))) : null
  );
}

function cvRow(cv, taskSlot, container) {
  const state = { ok: "read", pending: "queued", running: "reading", failed: "failed" }[cv.extract_state] || cv.extract_state;
  return el("div", { class: "source" },
    el("div", { class: "source-main" },
      el("div", { class: "name" },
        cv.label,
        cv.is_primary ? el("span", { class: "chip matched", text: "tailoring base" }) : null
      ),
      el("div", {
        class: `source-note${cv.extract_state === "failed" ? " warn" : ""}`,
        text: `${cv.filename} · ${state}${cv.extract_error ? ` · ${cv.extract_error}` : ""}`,
      })
    ),
    el("div", { class: "source-controls" },
      cv.is_primary
        ? null
        : el("button", {
            class: "ghost small",
            onClick: async () => {
              await api.primaryCv(cv.id);
              await renderProfile(container);
            },
          }, "Use for tailoring"),
      el("button", {
        class: "ghost small",
        onClick: async () => {
          try {
            const { task } = await api.reextract(cv.id);
            const view = new TaskView(task);
            taskSlot.append(view.node);
            await watch(task, { view });
            await renderProfile(container);
          } catch (error) {
            fail(error.message);
          }
        },
      }, "Read again"),
      el("button", {
        class: "danger small",
        onClick: async () => {
          if (!confirm(`Remove ${cv.label}? The profile is rebuilt from what is left.`)) return;
          await api.deleteCv(cv.id);
          await renderProfile(container);
        },
      }, "Remove")
    )
  );
}

// --- preferences -------------------------------------------------------------
function preferencesCard(data, container) {
  const titles = listInput(data.target_titles, "Site Reliability Engineer, Platform Engineer");
  const locations = listInput(data.locations, "London, Remote UK");
  const exclusions = listInput(data.exclusions, "sales, commission-only, night shift");
  const authorisation = el("input", { type: "text", value: data.work_authorization || "", placeholder: "e.g. UK citizen, no sponsorship needed" });
  const recency = el("input", { type: "number", min: "1", max: "90", value: data.recency_days || 7 });
  const seniority = el("select", {},
    ...["intern", "junior", "mid", "senior", "lead", "principal", "director"].map((level) =>
      el("option", { value: level, selected: data.seniority === level }, level)
    )
  );

  const chosenModes = new Set(data.work_modes || []);
  const modeChips = el("div", { class: "row tight" },
    ...WORK_MODES.map((mode) =>
      chipToggle(mode, chosenModes.has(mode), (on) => (on ? chosenModes.add(mode) : chosenModes.delete(mode)))
    )
  );

  const save = el("button", {
    onClick: async () => {
      save.disabled = true;
      try {
        await api.saveProfile({
          target_titles: readList(titles),
          locations: readList(locations),
          exclusions: readList(exclusions),
          work_modes: [...chosenModes],
          work_authorization: authorisation.value.trim(),
          recency_days: Number(recency.value) || 7,
          seniority: seniority.value,
        });
        ok("Saved. Existing scores are now stale and will be recalculated on the next run.");
        await app.refreshState();
        await renderProfile(container);
      } catch (error) {
        fail(error.message);
      } finally {
        save.disabled = false;
      }
    },
  }, "Save");

  // Filling in target titles from a blank box is the hardest question on this
  // screen, so the app offers an answer rather than only asking.
  const suggestionSlot = el("div", { class: "stack tight" });
  const suggestButton = el("button", {
    class: "ghost small",
    onClick: async () => {
      suggestButton.disabled = true;
      mount(suggestionSlot, el("div", { class: "loading-head" }, spinner(), el("span", { text: "Reading your profile" })));
      try {
        const result = await api.suggestRoles();
        mount(suggestionSlot, roleSuggestions(result, titles));
      } catch (error) {
        fail(error.message);
        mount(suggestionSlot, el("div", { class: "notice danger" }, el("p", { text: error.message })));
      } finally {
        suggestButton.disabled = false;
      }
    },
  }, "Suggest roles for me");

  return card(
    {
      title: "What you are looking for",
      subtitle: "These are the answers only you can give. Nothing read from a CV ever overwrites them.",
    },
    field("Target titles", titles, "Used to query the keyed APIs and to weight recall."),
    el("div", { class: "row tight" }, suggestButton),
    suggestionSlot,
    field("Locations", locations),
    field("Work modes", modeChips, "Postings that state a different mode are dropped before the model sees them. Ones that state nothing are kept."),
    field("Your level", seniority, "Postings more than one level above this are filtered out for free."),
    field("Work authorisation", authorisation, "Told to the model so it can rule out roles you genuinely cannot take."),
    field("Only show postings newer than", recency, "In days."),
    field("Never show me", exclusions, "Matched against the title and the company name."),
    el("div", { class: "row" }, save)
  );
}

/** Suggested titles, each a click away from being added to the box above. */
function roleSuggestions(result, titlesInput) {
  const roles = result.roles || [];
  if (!roles.length) {
    return el("div", { class: "notice" }, el("p", { text: result.note || "Nothing to suggest yet." }));
  }

  const add = (title) => {
    const current = readList(titlesInput);
    if (!current.some((item) => item.toLowerCase() === title.toLowerCase())) current.push(title);
    titlesInput.value = current.join(", ");
    ok(`Added "${title}". Press Save to keep it.`);
  };

  return el("div", { class: "stack tight" },
    el("p", { class: "muted small-text", style: { margin: 0 },
      text: result.note || (result.source === "model"
        ? "Judged from your CV by the model. Click one to add it, then Save."
        : "Worked out from your job titles. Click one to add it, then Save."),
    }),
    el("div", { class: "role-suggestions" },
      ...roles.map((role) =>
        el("button", {
          type: "button",
          class: `role-suggestion${role.reach === "stretch" ? " is-stretch" : ""}`,
          title: role.why || "",
          onClick: () => add(role.title),
        },
          el("span", { class: "role-title", text: role.title }),
          el("span", { class: "role-why", text: role.why || "" }),
          el("span", { class: "role-reach", text: role.reach === "stretch" ? "a step up" : "ready now" })
        )
      )
    )
  );
}

// --- what the merge produced --------------------------------------------------
function skillsCard(data) {
  const skills = data.skills || [];
  if (!skills.length) {
    return card(
      { title: "Skills" },
      el("p", { class: "muted", style: { margin: 0 }, text: "Upload a CV and the skills found in it appear here." })
    );
  }
  const core = skills.filter((skill) => skill.core);
  const rest = skills.filter((skill) => !skill.core);

  return card(
    {
      title: "Skills",
      subtitle: "Core means the skill appears in most of your CVs, so it carries more weight when matching.",
      actions: el("span", { class: "chip", text: String(skills.length) }),
    },
    core.length
      ? el("div", {}, el("h3", { text: "Core" }), el("div", { class: "chips" }, ...core.map(skillChip)))
      : null,
    rest.length
      ? el("div", {}, el("h3", { text: "Mentioned less often" }), el("div", { class: "chips" }, ...rest.map(skillChip)))
      : null
  );
}

function skillChip(skill) {
  const detail = [skill.level !== "unknown" ? skill.level : null, skill.years ? `${skill.years}y` : null]
    .filter(Boolean)
    .join(", ");
  return el("span", {
    class: skill.core ? "chip matched" : "chip",
    title: `Appears in ${Math.round((skill.confidence || 0) * 100)}% of your CVs`,
    text: detail ? `${skill.name} · ${detail}` : skill.name,
  });
}

function extractedCard(data) {
  if (!data.roles?.length && !data.headline) return null;
  return card(
    {
      title: "From your CVs",
      subtitle: `${plural(data.source_cv_count || 0, "CV")} merged · ${Math.round(data.total_years_experience || 0)} years · ${data.seniority || "unknown"} level`,
    },
    data.headline ? el("p", { style: { margin: 0 } }, el("strong", { text: data.headline })) : null,
    data.summary ? el("p", { class: "small-text muted", style: { margin: 0 }, text: data.summary }) : null,
    data.roles?.length
      ? el("details", {},
          el("summary", { text: `${plural(data.roles.length, "role")} found` }),
          rows(
            ...data.roles.map((role) =>
              el("div", { class: "status-line" },
                el("div", { class: "status-body" },
                  el("strong", { text: `${role.title}${role.company ? `, ${role.company}` : ""}` }),
                  el("span", { class: "small-text muted", text: [role.start, role.end].filter(Boolean).join(" - ") })
                )
              )
            )
          )
        )
      : null,
    data.domains?.length
      ? el("div", {},
          el("h3", { text: "Domains" }),
          el("div", { class: "chips" }, ...data.domains.map((domain) => el("span", { class: "chip", text: domain })))
        )
      : null
  );
}
