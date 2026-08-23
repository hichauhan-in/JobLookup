// Sources: what is on, what needs a key, what needs a company name, and the
// deliberately awkward path to enabling a logged-in portal.

import { api } from "../api.js";
import { accordion, card, el, field, helpButton, mount, openDialog, splitRows, toggle } from "../dom.js";
import { fail, ok, warn } from "../notify.js";
import { TaskView, watch } from "../tasks.js";

const SECRET_FIELDS = {
  adzuna: [["adzuna_app_id", "Application ID"], ["adzuna_app_key", "Application key"]],
  jooble: [["jooble", "API key"]],
  usajobs: [["usajobs_email", "Registered email"], ["usajobs", "Authorisation key"]],
  findwork: [["findwork", "API token"]],
  reed: [["reed", "API key"]],
};

// Company boards first: they are the ones worth spending five minutes on, and
// they are where the best postings come from.
const TIER_ORDER = ["ats", "a", "b"];

const TIERS = {
  ats: {
    title: "Company job boards",
    subtitle:
      "Watch specific companies. Each publishes its own openings, so these are the freshest and most complete postings anywhere and the apply link goes straight to the employer. Adding a few companies is the highest-value thing you can do on this screen.",
  },
  a: {
    title: "Public job APIs",
    subtitle:
      "Broad, general-purpose job feeds. Most need nothing at all; the rest want a free key, and each one tells you how to get it.",
  },
  b: {
    title: "Portals that need a login",
    subtitle:
      "LinkedIn, Indeed and the rest. Off by default, and off again per portal. Read the notice before enabling anything here.",
  },
};

//: Which sections are open. Survives the re-render that follows every toggle.
const openSections = { region: true, ats: false, a: false, b: false };
const SECTION_KEYS = ["region", ...TIER_ORDER];

//: The review panel stays open across re-renders, so applying a pack does not
//: immediately hide the list of what it just did.
let lastApplied = null;

export async function renderSources(container) {
  const [payload, secrets] = await Promise.all([api.sources(), api.get("/api/secrets")]);
  const taskSlot = el("div", { class: "stack tight" });
  const groups = { a: [], ats: [], b: [] };
  for (const source of payload.sources || []) groups[source.tier]?.push(source);
  const guided = payload.use_region !== false;

  const allOpen = SECTION_KEYS.every((key) => openSections[key]);
  const expander = el(
    "button",
    {
      class: "ghost small",
      onClick: async () => {
        for (const key of SECTION_KEYS) openSections[key] = !allOpen;
        await renderSources(container);
      },
    },
    allOpen ? "Collapse all" : "Expand all"
  );

  mount(
    container,
    el("div", { class: "page-head" },
      el("div", { class: "row between" },
        el("div", {},
          el("h1", { text: "Sources" }),
          el("p", { text: guided
            ? "Start at the top: pick where you are looking and let it set everything up. The sections below are the same sources in full, so you can adjust anything it chose."
            : "Guided setup is off, so this is the full list. Turn on what you want searched. Every source has a ? explaining exactly what it needs from you." })
        ),
        expander
      )
    ),
    el("div", { class: "stack" },
      taskSlot,
      regionCard(payload, secrets, taskSlot, container, guided),
      ...TIER_ORDER.map((tier) =>
        tier === "b"
          ? tierBCard(payload, groups.b, taskSlot, container)
          : tierCard(tier, groups[tier], secrets, taskSlot, container, payload)
      )
    )
  );
}

// --- reviewing what was configured --------------------------------------------
/** The companies a pack chose, so a setup that ran can actually be checked. */
function reviewPanel(applied, container) {
  if (!applied) return null;
  const companies = applied.companies || [];
  const byBoard = new Map();
  for (const entry of companies) {
    if (!byBoard.has(entry.board)) byBoard.set(entry.board, []);
    byBoard.get(entry.board).push(entry);
  }

  const dismiss = el("button", {
    class: "ghost small",
    onClick: async () => {
      lastApplied = null;
      await renderSources(container);
    },
  }, "Hide this");

  return el("div", { class: "review-panel" },
    el("div", { class: "row between" },
      el("div", {},
        el("strong", { text: `${applied.name} is set up` }),
        el("div", { class: "small-text muted", text: summarise(applied) })
      ),
      dismiss
    ),
    byBoard.size
      ? el("div", { class: "stack tight", style: { marginTop: "12px" } },
          ...[...byBoard.entries()].map(([board, entries]) =>
            el("details", { class: "source-detail" },
              el("summary", {},
                `${boardName(board)} · ${entries.length} companies`
              ),
              el("div", { class: "detail-body" },
                el("div", { class: "suggest-grid" },
                  ...entries.map((entry) =>
                    el("div", { class: "suggest-item" },
                      el("div", { class: "suggest-name" }, entry.name),
                      el("div", { class: "suggest-why", text: (entry.reasons || []).join(" · ") || "A solid employer" })
                    )
                  )
                )
              )
            )
          )
        )
      : null,
    applied.needs_setup?.length
      ? el("div", { class: "notice", style: { marginTop: "12px" } },
          el("p", { text: "Still needs you: " + applied.needs_setup.map((entry) => `${entry.name} (${entry.reason})`).join("; ") })
        )
      : null,
    applied.needs_login?.length
      ? el("p", { class: "small-text muted", style: { marginTop: "10px" },
          text: `${applied.needs_login.join(", ")} need a login, so they were left off. Turn them on in the logged-in portals section if you want them.`,
        })
      : null
  );
}

function summarise(applied) {
  const parts = [];
  const on = applied.enabled?.length || 0;
  if (on) parts.push(`${on} source${on === 1 ? "" : "s"} switched on`);
  if (applied.company_count) parts.push(`${applied.company_count} companies added`);
  if (applied.needs_setup?.length) parts.push(`${applied.needs_setup.length} still need a key or a company`);
  return parts.join(" · ") || "Nothing to change";
}

const BOARD_NAMES = {
  greenhouse: "Greenhouse", lever: "Lever", ashby: "Ashby", workable: "Workable",
  recruitee: "Recruitee", smartrecruiters: "SmartRecruiters", workday: "Workday",
  personio: "Personio",
};

function boardName(key) {
  return BOARD_NAMES[key] || key;
}

function remember(node, tier) {
  node.addEventListener("toggle", () => {
    openSections[tier] = node.open;
  });
  return node;
}

// --- guided setup -------------------------------------------------------------
// One place that configures everything, and one place that reports what it did.
// The sections below are the same sources in full; this is the shortlist for
// where you are, already filled in.
function regionCard(payload, secrets, taskSlot, container, guided) {
  const region = payload.region || {};
  const picks = region.picks || [];

  const master = toggle(guided, {
    label: "Use guided setup",
    onChange: async (value) => {
      try {
        await api.saveSettings({ search: { use_region: value } });
        ok(value
          ? "Guided setup is on. Pick where you are looking and press Set up."
          : "Guided setup is off. Configure the sections below however you like.");
        await renderSources(container);
      } catch (error) {
        master.checked = !value;
        fail(error.message);
      }
    },
  });

  const masterRow = el("div", { class: "setting span-all" },
    el("div", { class: "setting-label" },
      el("span", { class: "setting-title", text: "Use guided setup" }),
      el("span", { class: "setting-help", text: guided
        ? "On means this card sets up the sections below for you. Everything it chooses stays editable down there, and is labelled so you can tell its choices from yours."
        : "Off. Nothing is chosen for you: the sections below are the whole story and no country settings are applied." })
    ),
    el("div", { class: "setting-control" }, master)
  );

  if (!guided) {
    return remember(
      accordion(
        {
          title: "Guided setup",
          subtitle: "Off. You are configuring every source yourself in the sections below.",
          badge: el("span", { class: "chip", text: "off" }),
          open: openSections.region,
        },
        splitRows(masterRow),
        el("p", { class: "card-sub", style: { margin: 0 },
          text: "Turn this back on if you would rather say where you are looking and have the right sources, country settings and companies filled in for you.",
        })
      ),
      "region"
    );
  }

  const chooser = el("select", {},
    ...(payload.regions || []).map((entry) =>
      el("option", { value: entry.code, selected: entry.code === region.code }, entry.name)
    )
  );
  const count = el("select", {},
    ...[20, 40, 60, 100, 150].map((value) =>
      el("option", { value: String(value), selected: value === 60 }, `${value} companies`)
    )
  );

  const setUp = async () => {
    applyButton.disabled = true;
    applyButton.textContent = "Setting up...";
    try {
      const result = await api.setRegion(chooser.value, true, { companies: Number(count.value) });
      lastApplied = result.applied;
      ok(`${result.applied?.name}: ${summarise(result.applied)}.`);
      await renderSources(container);
    } catch (error) {
      fail(error.message);
      applyButton.disabled = false;
      applyButton.textContent = "Set up everything";
    }
  };

  chooser.addEventListener("change", async () => {
    chooser.disabled = true;
    try {
      const result = await api.setRegion(chooser.value, false);
      lastApplied = null;
      ok(`Showing what works in ${result.region?.name || chooser.value}. Press Set up everything to apply it.`);
      await renderSources(container);
    } catch (error) {
      fail(error.message);
      chooser.disabled = false;
    }
  });

  const applyButton = el("button", { class: "small", onClick: setUp }, "Set up everything");
  const clearButton = el("button", {
    class: "ghost small",
    onClick: async () => {
      if (!confirm(`Undo what the ${region.name} pack configured? Companies you added yourself are kept.`)) return;
      try {
        const result = await api.clearRegion();
        lastApplied = null;
        ok(result.cleared?.cleared?.length
          ? `Cleared ${result.cleared.cleared.length} source(s).`
          : "There was nothing from this pack to clear.");
        await renderSources(container);
      } catch (error) {
        fail(error.message);
      }
    },
  }, "Undo this pack");

  const ready = picks.filter((pick) => pick.enabled && pick.ready).length;
  const managed = picks.filter((pick) => pick.config?.from_region === region.code).length;

  const remoteOnly = toggle(Boolean(payload.remote_only), {
    label: "Only show remote roles",
    disabled: region.remote_only,
    onChange: async (value) => {
      try {
        await api.setRemoteOnly(value);
        ok(value
          ? "Only remote roles will be kept, wherever they are."
          : "Office-based roles are included again.");
        await renderSources(container);
      } catch (error) {
        remoteOnly.checked = !value;
        fail(error.message);
      }
    },
  });

  return remember(
    accordion(
      {
        title: "Where are you looking?",
        subtitle:
          "Pick a country and press Set up everything. It switches on the sources worth your time there, fills in that country's settings, and gives every company board a list of employers ranked against your CV. All of it stays editable in the sections below.",
        badge: el("span", { class: "chip", text: `${region.name || "India"} · ${ready} of ${picks.length} on` }),
        open: openSections.region,
      },
      splitRows(
        masterRow,
        el("div", { class: "setting span-all" },
          el("div", { class: "setting-label" },
            el("span", { class: "setting-title", text: "Country or remote" }),
            el("span", { class: "setting-help", text: "Changing this only changes what is shown here. Nothing is applied until you press the button." })
          ),
          el("div", { class: "setting-control" }, chooser)
        ),
        el("div", { class: "setting span-all" },
          el("div", { class: "setting-label" },
            el("span", { class: "setting-title", text: "Companies to watch" }),
            el("span", { class: "setting-help", text: "Spread across this pack's company boards, ranked for this country and your CV. More companies means a slower search, not a worse one." })
          ),
          el("div", { class: "setting-control" }, count)
        ),
        el("div", { class: "setting span-all" },
          el("div", { class: "setting-label" },
            el("span", { class: "setting-title", text: "Only show remote roles" }),
            el("span", {
              class: "setting-help",
              text: region.remote_only
                ? "Always on for the Remote pack. Pick a country above if you want remote roles in one place instead of anywhere."
                : `Combines with the country above, so you can search ${region.name || "one country"} and keep only the roles you can do from home.`,
            })
          ),
          el("div", { class: "setting-control" }, remoteOnly)
        )
      ),
      el("div", { class: "row" }, applyButton, managed ? clearButton : null),
      region.summary ? el("p", { class: "card-sub", style: { margin: "4px 0 0" }, text: region.summary }) : null,
      reviewPanel(lastApplied, container),
      region.remote_only || payload.remote_only
        ? el("div", { class: "notice info" },
            el("p", { text: "Remote filtering is on: anything not positively identified as a remote role is dropped before it is scored." })
          )
        : null,
      el("h3", { text: "What this pack uses", style: { margin: "8px 0 0" } }),
      splitRows(...picks.map((pick) => sourceRow(pick, secrets, taskSlot, container, pick.why))),
      region.note ? el("div", { class: "notice" }, el("p", { text: region.note })) : null
    ),
    "region"
  );
}

function tierCard(tier, sources, secrets, taskSlot, container, payload) {
  const enabled = sources.filter((source) => source.enabled).length;
  const regionCode = payload?.region?.code;
  const fromPack = sources.filter((source) => source.config?.from_region === regionCode).length;

  return remember(
    accordion(
      {
        title: TIERS[tier].title,
        subtitle: TIERS[tier].subtitle,
        badge: el("div", { class: "row tight" },
          fromPack
            ? el("span", { class: "chip matched", text: `${fromPack} from your pack` })
            : null,
          el("span", { class: "chip", text: `${enabled} of ${sources.length} on` })
        ),
        open: openSections[tier],
      },
      splitRows(
        ...sources.map((source) => sourceRow(source, secrets, taskSlot, container, "", payload))
      )
    ),
    tier
  );
}

function sourceRow(source, secrets, taskSlot, container, why = "", payload = null) {
  const control = toggle(source.enabled, {
    // A portal cannot be switched on from here: it needs the master switch and
    // its own risk acknowledgement, both of which live in the section below.
    disabled: Boolean(why) && source.is_tier_b,
    label: `Enable ${source.name}`,
    onChange: async (value) => {
      try {
        await api.toggleSource(source.key, value);
        await renderSources(container);
      } catch (error) {
        control.checked = !value;
        fail(error.message);
      }
    },
  });

  const companies = source.config?.slugs || [];
  const managed = source.config?.from_region;
  const regionName = payload?.region?.name;

  return el("div", { class: `source${source.enabled && !source.ready ? " blocked" : ""}` },
    el("div", { class: "source-main" },
      el("div", { class: "name" },
        source.name,
        el("span", { class: `tier ${source.tier}`, text: source.tier === "a" ? "api" : source.tier }),
        // Where a list came from, so the pack's choices are never mistaken for
        // your own and can be told apart at a glance.
        managed && managed === payload?.region?.code
          ? el("span", { class: "chip matched", title: `Chosen by your ${regionName} pack. Edit it below and it becomes yours.`, text: "from pack" })
          : null,
        companies.length
          ? el("span", { class: "chip", text: `${companies.length} ${companies.length === 1 ? "company" : "companies"}` })
          : null
      ),
      why ? el("div", { class: "source-why", text: why }) : null,
      statusNote(source),
      companies.length ? companyPreview(source, companies) : null,
      why && source.is_tier_b
        ? el("div", { class: "source-note warn", text: "Turn this on in the logged-in portals section below, after reading the notice." })
        : null,
      source.fields?.length || SECRET_FIELDS[source.key]
        ? el("div", { class: "source-extras" },
            source.fields?.length ? configPanel(source, container) : null,
            SECRET_FIELDS[source.key] ? secretPanel(source, secrets, container) : null
          )
        : null
    ),
    el("div", { class: "source-controls" },
      helpButton(`How to set up ${source.name}`, () => showGuide(source)),
      source.homepage
        ? el("a", { class: "source-link", href: source.homepage, target: "_blank", rel: "noopener noreferrer" }, "Site")
        : null,
      control
    )
  );
}

/** The first few companies inline, so a configured board shows it at a glance. */
function companyPreview(source, companies) {
  const shown = companies.slice(0, 6);
  return el("div", { class: "company-preview" },
    ...shown.map((slug) => el("span", { class: "company-pill", title: slug, text: shortName(slug) })),
    companies.length > shown.length
      ? el("button", {
          class: "company-pill more",
          onClick: () => openDialog(
            { title: `${source.name}`, subtitle: `${companies.length} companies being watched` },
            el("div", { class: "company-preview wrap" },
              ...companies.map((slug) => el("span", { class: "company-pill", title: slug, text: shortName(slug) }))
            )
          ),
        }, `+${companies.length - shown.length} more`)
      : null
  );
}

/** Workday is addressed by URL, which is unreadable as a pill. Show the tenant. */
function shortName(slug) {
  if (!slug.startsWith("http")) return slug;
  const host = slug.split("://")[1]?.split("/")[0] || slug;
  return host.split(".")[0];
}

/** Everything this particular source wants from you, in the order it wants it. */
function showGuide(source) {
  const guide = source.guide || {};
  openDialog(
    { title: `Setting up ${source.name}`, subtitle: guide.summary || source.description || "" },
    guide.facts?.length
      ? el("div", {},
          el("h3", { text: "At a glance" }),
          el("dl", { class: "guide-facts" },
            ...guide.facts.flatMap((fact) => [
              el("dt", { text: fact.label }),
              el("dd", { text: fact.value }),
            ])
          )
        )
      : null,
    guide.steps?.length
      ? el("div", {},
          el("h3", { text: "What to do" }),
          el("ol", { class: "steps-list" }, ...guide.steps.map((step) => el("li", { text: step })))
        )
      : null,
    guide.examples?.length
      ? el("div", {},
          el("h3", { text: "Examples" }),
          el("div", { class: "guide-examples" },
            ...guide.examples.map((example) =>
              el("div", { class: "guide-example" },
                el("span", { class: "seen", text: example.seen }),
                el("span", { class: "enter", text: example.enter })
              )
            )
          )
        )
      : null,
    guide.links?.length
      ? el("div", { class: "row" },
          ...guide.links.map((link) =>
            el("a", { class: "btn ghost", href: link.url, target: "_blank", rel: "noopener noreferrer" }, link.label)
          )
        )
      : null,
    guide.note ? el("div", { class: "notice info" }, el("p", { text: guide.note })) : null
  );
}

function statusNote(source) {
  if (source.enabled && !source.ready) {
    return el("div", { class: "source-note warn", text: source.blocked_reason });
  }
  if (source.enabled) return el("div", { class: "source-note", text: lastRun(source) });
  return el("div", { class: "source-note", text: source.description });
}

function lastRun(source) {
  if (!source.last_run_at) return "On. Not run yet.";
  if (source.last_status === "failed") {
    return `Last run failed: ${source.last_error || "unknown reason"}`;
  }
  return `Last run returned ${source.last_count} posting(s).`;
}

function configPanel(source, container) {
  const inputs = source.fields.map((spec) => {
    const value = source.config?.[spec.key];
    const control =
      spec.kind === "list"
        ? el("textarea", { rows: 2, placeholder: spec.placeholder, value: (value || []).join(", ") })
        : el("input", {
            type: spec.kind === "number" ? "number" : "text",
            placeholder: spec.placeholder,
            value: value ?? "",
          });
    return { spec, control };
  });

  const save = el("button", {
    class: "ghost small",
    onClick: async () => {
      const config = {};
      for (const { spec, control } of inputs) {
        config[spec.key] =
          spec.kind === "list"
            ? control.value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean)
            : control.value.trim();
      }
      try {
        await api.configureSource(source.key, config);
        ok(`${source.name} updated.`);
        await renderSources(container);
      } catch (error) {
        fail(error.message);
      }
    },
  }, "Save");

  return el("details", { class: "source-detail", open: source.enabled && !source.ready },
    el("summary", { text: "Configure" }),
    el("div", { class: "detail-body" },
      ...inputs.map(({ spec, control }) => field(spec.label, control, spec.help)),
      el("div", { class: "row" }, save)
    )
  );
}

function secretPanel(source, secrets, container) {
  const fields = SECRET_FIELDS[source.key] || [];
  const inputs = fields.map(([name, label]) => ({
    name,
    label,
    control: el("input", {
      type: name.includes("email") ? "text" : "password",
      placeholder: secrets?.set?.[name] ? "Stored. Leave blank to keep it." : "Not set",
    }),
  }));

  const save = el("button", {
    class: "ghost small",
    onClick: async () => {
      try {
        for (const entry of inputs) {
          if (entry.control.value.trim()) await api.setSecret(entry.name, entry.control.value.trim());
        }
        ok("Keys stored.");
        await renderSources(container);
      } catch (error) {
        fail(error.message);
      }
    },
  }, "Store keys");

  const where = secrets?.backend === "keyring" ? "Windows Credential Manager" : "an owner-only local file";

  return el("details", { class: "source-detail" },
    el("summary", { text: "API keys" }),
    el("div", { class: "detail-body" },
      ...inputs.map((entry) => field(entry.label, entry.control)),
      el("div", { class: "field-help", text: `Stored in ${where}. Never written to a config file.` }),
      el("div", { class: "row" }, save)
    )
  );
}

// --- logged-in portals --------------------------------------------------------
function tierBCard(payload, portals, taskSlot, container) {
  const master = toggle(payload.tier_b_enabled, {
    label: "Allow logged-in portal automation",
    onChange: async (value) => {
      try {
        await api.saveSettings({ tier_b: { enabled: value } });
        await renderSources(container);
      } catch (error) {
        master.checked = !value;
        fail(error.message);
      }
    },
  });

  const playwright = payload.playwright || {};
  const enabled = portals.filter((portal) => portal.enabled).length;

  const installButton = el("button", {
    class: "ghost small",
    onClick: async () => {
      installButton.disabled = true;
      try {
        const { task } = await api.installPlaywright();
        const view = new TaskView(task);
        mount(taskSlot, view.node);
        await watch(task, { view });
        ok("Playwright installed.");
        await renderSources(container);
      } catch (error) {
        fail(error.message);
      } finally {
        installButton.disabled = false;
      }
    },
  }, "Install Playwright and Chromium");

  return remember(
    accordion(
      {
        title: TIERS.b.title,
        subtitle: TIERS.b.subtitle,
        badge: el("span", {
          class: "chip",
          text: payload.tier_b_enabled ? `${enabled} of ${portals.length} on` : "off",
        }),
        open: openSections.b,
      },
      el("div", { class: "notice danger" }, el("p", { text: payload.risk_notice })),
      splitRows(
        el("div", { class: "setting span-all" },
          el("div", { class: "setting-label" },
            el("span", { class: "setting-title", text: "Allow logged-in portal automation" }),
            el("span", {
              class: "setting-help",
              text: "The master switch. Nothing below can run until this is on, and each portal still has to be acknowledged and enabled on its own.",
            })
          ),
          el("div", { class: "setting-control" }, master)
        )
      ),

      payload.tier_b_enabled && !playwright.browser_ready
        ? el("div", { class: "notice" },
            el("p", { text: playwright.detail || "Playwright is not ready." }),
            el("div", { class: "row", style: { marginTop: "12px" } }, installButton),
            playwright.fix ? el("div", { class: "mono", style: { marginTop: "10px" }, text: playwright.fix }) : null
          )
        : null,

      payload.tier_b_enabled ? splitRows(...portals.map((portal) => portalRow(portal, taskSlot, container))) : null
    ),
    "b"
  );
}

function portalRow(portal, taskSlot, container) {
  const ack = toggle(portal.risk_ack, {
    label: `Accept the risk for ${portal.name}`,
    title: "Acknowledge the terms-of-service risk",
    onChange: async (value) => {
      if (value && !confirm(`Using ${portal.name} this way is against its terms of service and can get your account banned. Continue?`)) {
        ack.checked = false;
        return;
      }
      await api.ackRisk(portal.key, value);
      await renderSources(container);
    },
  });

  const enable = toggle(portal.enabled, {
    disabled: !portal.risk_ack,
    label: `Enable ${portal.name}`,
    onChange: async (value) => {
      try {
        await api.toggleSource(portal.key, value);
        await renderSources(container);
      } catch (error) {
        enable.checked = !value;
        fail(error.message);
      }
    },
  });

  const runTask = async (starter, label) => {
    try {
      const { task } = await starter();
      const view = new TaskView(task);
      mount(taskSlot, view.node);
      const result = await watch(task, { view });
      if (result.selectors) reportSelectors(taskSlot, portal, result);
      else if (result.session_saved) ok(`${portal.name} session saved.`);
      else warn(`No ${portal.name} session was saved. Sign in fully before closing the window.`);
      await renderSources(container);
    } catch (error) {
      fail(`${label} failed: ${error.message}`);
    }
  };

  return el("div", { class: `source${portal.enabled && !portal.ready ? " blocked" : ""}` },
    el("div", { class: "source-main" },
      el("div", { class: "name" }, portal.name, el("span", { class: "tier b", text: "login" })),
      statusNote(portal),
      el("div", { class: "row tight", style: { marginTop: "4px" } },
        el("button", {
          class: "ghost small",
          disabled: !portal.risk_ack,
          onClick: () => runTask(() => api.signIn(portal.key), "Sign in"),
        }, "Sign in"),
        el("button", {
          class: "ghost small",
          disabled: !portal.risk_ack,
          onClick: () => runTask(() => api.testSelectors(portal.key), "Selector test"),
        }, "Test selectors")
      )
    ),
    el("div", { class: "source-controls" },
      helpButton(`How to set up ${portal.name}`, () => showGuide(portal)),
      el("div", { class: "row tight" }, el("span", { class: "small-text muted", text: "Risk" }), ack),
      el("div", { class: "row tight" }, el("span", { class: "small-text muted", text: "On" }), enable)
    )
  );
}

function reportSelectors(slot, portal, report) {
  const list = Object.entries(report.selectors || {}).map(([name, info]) =>
    el("tr", {},
      el("td", { text: name }),
      el("td", { class: "mono", text: info.selector || "" }),
      el("td", { text: String(info.matched ?? 0) }),
      el("td", { class: "muted", text: info.sample || info.error || "" })
    )
  );

  slot.append(
    card({ title: `${portal.name} selector test`, subtitle: report.url || "" },
      report.logged_out
        ? el("div", { class: "notice danger", text: "The portal showed a sign-in wall. Sign in again before testing." })
        : null,
      el("table", {},
        el("thead", {}, el("tr", {},
          el("th", { text: "Field" }), el("th", { text: "Selector" }),
          el("th", { text: "Matched" }), el("th", { text: "Sample" })
        )),
        el("tbody", {}, ...list)
      ),
      el("p", {
        class: "muted small-text",
        style: { margin: 0 },
        text: `Zero matches means the portal changed its layout. Edit ${report.file} and test again - no Python involved.`,
      })
    )
  );
}
