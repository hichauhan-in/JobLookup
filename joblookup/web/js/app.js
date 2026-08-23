// The shell: navigation, the status pill, the theme, and a hash router.

import { api } from "./api.js";
import { startBridgeWatch } from "./bridgealert.js";
import { clear, el, mount, spinner } from "./dom.js";
import { fail } from "./notify.js";
import { renderTaskFooter } from "./tasks.js";

import { renderApplications } from "./views/applications.js";
import { renderDashboard } from "./views/dashboard.js";
import { renderHistory } from "./views/history.js";
import { renderJob } from "./views/job.js";
import { renderMatches } from "./views/matches.js";
import { renderProfile } from "./views/profile.js";
import { renderSettings } from "./views/settings.js";
import { renderSources } from "./views/sources.js";

export const app = {
  state: null,
  async refreshState() {
    this.state = await api.state();
    paintStatus(this.state);
    paintNav(this.state);
    return this.state;
  },
  go(route) {
    location.hash = route.startsWith("#") ? route : `#${route}`;
  },
};

// In the order the work actually happens: say who you are, see what came back,
// track what you did about it, then the setup you rarely revisit.
const ROUTES = [
  { path: "dashboard", label: "Dashboard", render: renderDashboard },
  { path: "profile", label: "Profile", render: renderProfile },
  { path: "matches", label: "Matches", render: renderMatches, count: (s) => s.counts?.scored },
  { path: "applications", label: "Applications", render: renderApplications, count: (s) => s.counts?.tracked },
  { path: "sources", label: "Sources", render: renderSources, count: (s) => s.counts?.sources_enabled },
  { path: "history", label: "History", render: renderHistory },
  { path: "settings", label: "Settings", render: renderSettings },
];

const main = () => document.getElementById("main");

// --- navigation --------------------------------------------------------------
function paintNav(state) {
  const nav = document.getElementById("nav");
  const current = currentRoute().name;
  clear(nav);
  for (const route of ROUTES) {
    const count = route.count?.(state || {});
    nav.append(
      el(
        "button",
        {
          class: route.path === current ? "active" : "",
          onClick: () => app.go(`/${route.path}`),
        },
        el("span", { text: route.label }),
        count ? el("span", { class: "count", text: String(count) }) : null
      )
    );
  }
}

function paintStatus(state) {
  const pill = document.getElementById("statusPill");
  const provider = state?.provider || {};
  const good = Boolean(provider.available);
  pill.className = `pill ${good ? "pill-ok" : "pill-bad"}`;
  pill.title = provider.detail || "";
  mount(
    pill,
    el("i", { class: "dot" }),
    el("span", { text: good ? provider.active_model || "Ready" : "No model" })
  );
}

// --- routing -----------------------------------------------------------------
function currentRoute() {
  const raw = (location.hash || "#/dashboard").slice(1);
  const [path, query = ""] = raw.split("?");
  const [name, ...rest] = path.split("/").filter(Boolean);
  return { name: name || "dashboard", params: rest, query: new URLSearchParams(query) };
}

//: Bumped on every navigation. A render that finishes after this has moved on
//: belongs to a screen the user has already left, so it is thrown away rather
//: than mounted - which is what used to make the view jump on its own.
let generation = 0;

async function draw() {
  const token = ++generation;
  const { name, params, query } = currentRoute();

  // Highlight the destination before any awaiting, so the click feels instant.
  paintNav(app.state);

  // Each draw renders into its own element and only that element is attached.
  // A stale render therefore fills a node that is never shown, and cannot
  // overwrite whatever the user is looking at now.
  const container = el("div", { class: "view" });
  mount(main(), loadingPanel(name));

  try {
    if (name === "job" && params[0]) {
      await renderJob(container, Number(params[0]));
    } else {
      const route = ROUTES.find((entry) => entry.path === name) || ROUTES[0];
      await route.render(container, query);
    }
  } catch (error) {
    if (token !== generation) return;
    mount(
      container,
      el("div", { class: "notice danger" },
        el("strong", { text: "This screen could not load" }),
        el("div", { class: "small-text", text: error.message })
      )
    );
  }

  if (token !== generation) return;
  mount(main(), container);
  paintNav(app.state);
}

//: Screens that always take a moment, because they ask several things at once.
const SLOW = {
  dashboard: "Reading your counts and recent searches",
  settings: "Reading your settings",
  sources: "Reading the state of every source",
  matches: "Loading your matches",
  history: "Reading your past searches",
  profile: "Reading your CVs and profile",
  applications: "Reading what you have applied to",
  job: "Opening this posting",
};

/**
 * A skeleton shaped like the page that is coming, rather than the word
 * "Loading". It sits where the real content will sit, so nothing jumps when the
 * screen arrives.
 */
function loadingPanel(name) {
  return el("div", { class: "view loading-view" },
    el("div", { class: "loading-head" },
      spinner(22),
      el("div", { class: "loading-copy" },
        el("strong", { text: "Loading" }),
        el("span", { class: "small-text muted", text: SLOW[name] || "One moment" })
      )
    ),
    el("div", { class: "skeleton-stack" },
      el("div", { class: "skeleton tall" }),
      el("div", { class: "skeleton" }),
      el("div", { class: "skeleton short" })
    )
  );
}

// --- theme -------------------------------------------------------------------
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("joblookup.theme", theme);
  document.getElementById("themeToggle").textContent =
    theme === "light" ? "Dark theme" : "Light theme";
}

// --- quitting ----------------------------------------------------------------
/** Stop the server and say so, because the tab cannot close itself. */
async function quit(button) {
  if (!confirm("Close JobLookup? Any search still running will be stopped.")) return;
  button.disabled = true;
  button.textContent = "Closing...";
  try {
    await api.post("/api/quit");
  } catch (error) {
    // A dropped connection is the expected outcome: the server stops mid-reply.
    if (!/failed|network|fetch/i.test(error.message)) {
      button.disabled = false;
      button.textContent = "Close JobLookup";
      fail(error.message);
      return;
    }
  }
  document.title = "JobLookup has closed";
  mount(document.body, farewell());
}

/** The last thing you see. A closed app should look closed, not broken. */
function farewell() {
  return el("div", { class: "farewell" },
    el("div", { class: "farewell-card", role: "status" },
      el("div", { class: "farewell-mark" },
        el("span", { class: "farewell-tick", text: "\u2713" })
      ),
      el("h1", { text: "JobLookup has closed" }),
      el("p", { text: "The server has stopped and nothing is left running in the background. You can close this tab." }),
      el("div", { class: "farewell-restart" },
        el("span", { class: "small-text muted", text: "To start it again" }),
        el("code", { text: "Start JobLookup.cmd" })
      ),
      el("p", { class: "farewell-foot small-text muted", text: "Everything you collected is saved in your workspace folder and will be there next time." })
    )
  );
}

// --- start -------------------------------------------------------------------
async function start() {
  applyTheme(localStorage.getItem("joblookup.theme") || "dark");
  document.getElementById("themeToggle").addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
  });
  const quitButton = document.getElementById("quitApp");
  quitButton.addEventListener("click", () => quit(quitButton));
  // The pill names the model in use, so it should land on where you change it.
  document.getElementById("statusPill").addEventListener("click", () => app.go("/settings?focus=model"));

  renderTaskFooter(document.getElementById("tasksFoot"));
  window.addEventListener("hashchange", draw);

  try {
    await app.refreshState();
  } catch (error) {
    fail(error.message);
  }

  startBridgeWatch((state) => {
    app.state = state;
    paintStatus(state);
    paintNav(state);
  });

  if (!location.hash) location.hash = "#/dashboard";
  await draw();
}

start();
