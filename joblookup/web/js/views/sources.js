// Sources: what is on, what needs a key, what needs a company name, and the
// deliberately awkward path to enabling a logged-in portal.

import { api } from "../api.js";
import { accordion, card, el, field, helpButton, mount, openDialog, spinner, splitRows, toggle } from "../dom.js";
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

export async function renderSources(container) {
  const [payload, secrets] = await Promise.all([api.sources(), api.get("/api/secrets")]);
  const taskSlot = el("div", { class: "stack tight" });
  const groups = { a: [], ats: [], b: [] };
  for (const source of payload.sources || []) groups[source.tier]?.push(source);

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
          el("p", { text: "Turn on what you want searched. Every source has a ? explaining exactly what it needs from you." })
        ),
        expander
      )
    ),
    el("div", { class: "stack" },
      taskSlot,
      suggestCard(container),
      regionCard(payload, secrets, taskSlot, container),
      ...TIER_ORDER.map((tier) =>
        tier === "b"
          ? tierBCard(payload, groups.b, taskSlot, container)
          : tierCard(tier, groups[tier], secrets, taskSlot, container)
      )
    )
  );
}

// --- company suggestions ------------------------------------------------------
// Company boards are the best source of postings and the one thing the app
// cannot set up for you, because it needs a list of company names. This picks
// that list from a catalogue that was checked against the live APIs, ranked
// against your profile, so nobody has to sit and think of companies.
function suggestCard(container) {
  const body = el("div", { class: "stack tight" });
  const count = el("select", {},
    ...[25, 50, 100, 150].map((value) =>
      el("option", { value: String(value), selected: value === 100 }, `${value} companies`)
    )
  );
  const replace = toggle(false, { label: "Replace what is already there" });

  const run = async (apply) => {
    preview.disabled = true;
    applyButton.disabled = true;
    mount(body, el("div", { class: "loading-head" }, spinner(), el("span", { text: "Ranking companies against your profile" })));
    try {
      const result = await api.suggestCompanies({
        limit: Number(count.value),
        apply,
        replace: replace.checked,
      });
      mount(body, suggestionResult(result, apply));
      if (apply) {
        const total = Object.values(result.applied || {}).reduce((sum, n) => sum + n, 0);
        ok(`${total} companies are now being watched across ${Object.keys(result.applied || {}).length} boards.`);
        await renderSources(container);
      }
    } catch (error) {
      fail(error.message);
      mount(body, el("div", { class: "notice danger" }, el("p", { text: error.message })));
    } finally {
      preview.disabled = false;
      applyButton.disabled = false;
    }
  };

  const preview = el("button", { class: "ghost small", onClick: () => run(false) }, "Show me the list");
  const applyButton = el("button", { class: "small", onClick: () => run(true) }, "Add them to my boards");

  return accordion(
    {
      title: "Not sure which companies to watch?",
      subtitle:
        "Company boards are where the best postings come from, but they need company names. This picks them for you from a catalogue of employers whose boards were checked against the live APIs, ranked against your CV and what you are looking for.",
      badge: el("span", { class: "chip", text: "suggested for you" }),
      open: false,
    },
    splitRows(
      el("div", { class: "setting span-all" },
        el("div", { class: "setting-label" },
          el("span", { class: "setting-title", text: "How many to add" }),
          el("span", { class: "setting-help", text: "Spread across the boards so no single one dominates. More companies means a slower search, not a worse one." })
        ),
        el("div", { class: "setting-control" }, count)
      ),
      el("div", { class: "setting span-all" },
        el("div", { class: "setting-label" },
          el("span", { class: "setting-title", text: "Replace what is already there" }),
          el("span", { class: "setting-help", text: "Off adds to your existing companies and keeps them. On starts the list again from these suggestions." })
        ),
        el("div", { class: "setting-control" }, replace)
      )
    ),
    el("div", { class: "row" }, preview, applyButton),
    body
  );
}

function suggestionResult(result, applied) {
  const picks = result.suggestions || [];
  if (!picks.length) {
    return el("div", { class: "notice" },
      el("p", { text: "Nothing to suggest yet. Add a CV on the Profile screen so there is something to rank against." })
    );
  }

  const tags = result.tags || [];
  return el("div", { class: "stack tight" },
    el("p", { class: "card-sub", style: { margin: 0 },
      text: tags.length
        ? `Ranked against your profile, which reads as: ${tags.join(", ")}. Every board here was confirmed working on ${result.verified_on}.`
        : `Your profile has nothing to rank against yet, so these are simply the largest and best-paying employers in the catalogue. Every board was confirmed working on ${result.verified_on}.`,
    }),
    el("div", { class: "suggest-grid" },
      ...picks.slice(0, 60).map((pick) =>
        el("div", { class: "suggest-item" },
          el("div", { class: "suggest-name" },
            pick.name,
            el("span", { class: `tier ats`, text: pick.board })
          ),
          el("div", { class: "suggest-why", text: (pick.reasons || []).join(" · ") || "A solid employer" })
        )
      )
    ),
    picks.length > 60
      ? el("p", { class: "muted small-text", text: `and ${picks.length - 60} more` })
      : null,
    applied
      ? null
      : el("p", { class: "muted small-text", text: "Nothing has changed yet. Press Add them to my boards to start watching these." })
  );
}

function remember(node, tier) {
  node.addEventListener("toggle", () => {
    openSections[tier] = node.open;
  });
  return node;
}

// --- where you are looking ----------------------------------------------------
// The same sources as the three sections below, but ordered by what is actually
// worth your time in one country, with that country's settings filled in.
function regionCard(payload, secrets, taskSlot, container) {
  const region = payload.region || {};
  const picks = region.picks || [];

  const chooser = el("select", {},
    ...(payload.regions || []).map((entry) =>
      el("option", { value: entry.code, selected: entry.code === region.code }, entry.name)
    )
  );

  const choose = async (apply) => {
    chooser.disabled = true;
    try {
      const result = await api.setRegion(chooser.value, apply);
      if (apply) reportApplied(result.applied);
      else ok(`Showing what works in ${result.region?.name || chooser.value}.`);
      await renderSources(container);
    } catch (error) {
      fail(error.message);
      chooser.disabled = false;
    }
  };

  chooser.addEventListener("change", () => choose(false));

  const applyButton = el("button", { class: "ghost small", onClick: () => choose(true) },
    "Set up this pack");

  const ready = picks.filter((pick) => pick.enabled && pick.ready).length;

  // Independent of the pack, so "India, but only remote roles" is expressible.
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
          "The same sources as the sections below, ordered by what actually works in one country, with that country's settings filled in. Nothing here is a different source; it is the shortlist worth your time where you are.",
        badge: el("span", { class: "chip", text: `${region.name || "India"} · ${ready} of ${picks.length} on` }),
        open: openSections.region,
      },
      splitRows(
        el("div", { class: "setting span-all" },
          el("div", { class: "setting-label" },
            el("span", { class: "setting-title", text: "Country or remote" }),
            el("span", {
              class: "setting-help",
              text: "Changing this only changes what is shown. Press Set up this pack to switch on everything in it that can already run.",
            })
          ),
          el("div", { class: "setting-control" }, el("div", { class: "row tight" }, chooser, applyButton))
        ),
        el("div", { class: "setting span-all" },
          el("div", { class: "setting-label" },
            el("span", { class: "setting-title", text: "Only show remote roles" }),
            el("span", {
              class: "setting-help",
              text: region.remote_only
                ? "Always on for the Remote pack. Pick a country above if you want remote roles in one place instead of anywhere."
                : `Combines with the country above, so you can search ${region.name || "one country"} and keep only the roles you can do from home. Anything not positively identified as remote is dropped.`,
            })
          ),
          el("div", { class: "setting-control" }, remoteOnly)
        )
      ),
      region.summary ? el("p", { class: "card-sub", style: { margin: "4px 0 0" }, text: region.summary }) : null,
      region.remote_only || payload.remote_only
        ? el("div", { class: "notice info" },
            el("p", { text: "Remote filtering is on: anything not positively identified as a remote role is dropped before it is scored." })
          )
        : null,
      splitRows(...picks.map((pick) => sourceRow(pick, secrets, taskSlot, container, pick.why))),
      region.note ? el("div", { class: "notice" }, el("p", { text: region.note })) : null
    ),
    "region"
  );
}

function reportApplied(applied) {
  if (!applied) return;
  const parts = [];
  if (applied.enabled?.length) parts.push(`Switched on ${applied.enabled.length}`);
  if (applied.needs_setup?.length) {
    const n = applied.needs_setup.length;
    parts.push(`${n} still ${n === 1 ? "needs" : "need"} a key or a company`);
  }
  if (applied.needs_login?.length) {
    const n = applied.needs_login.length;
    parts.push(`${n} ${n === 1 ? "needs" : "need"} a login`);
  }
  const summary = parts.join(". ") || "Nothing to change";
  if (applied.needs_setup?.length || applied.needs_login?.length) warn(`${applied.name}: ${summary}.`);
  else ok(`${applied.name}: ${summary}.`);
}

function tierCard(tier, sources, secrets, taskSlot, container) {
  const enabled = sources.filter((source) => source.enabled).length;
  return remember(
    accordion(
      {
        title: TIERS[tier].title,
        subtitle: TIERS[tier].subtitle,
        badge: el("span", { class: "chip", text: `${enabled} of ${sources.length} on` }),
        open: openSections[tier],
      },
      splitRows(...sources.map((source) => sourceRow(source, secrets, taskSlot, container)))
    ),
    tier
  );
}

function sourceRow(source, secrets, taskSlot, container, why = "") {
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

  return el("div", { class: `source${source.enabled && !source.ready ? " blocked" : ""}` },
    el("div", { class: "source-main" },
      el("div", { class: "name" },
        source.name,
        el("span", { class: `tier ${source.tier}`, text: source.tier === "a" ? "api" : source.tier })
      ),
      why ? el("div", { class: "source-why", text: why }) : null,
      statusNote(source),
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
