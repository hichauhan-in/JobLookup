// Telling the user exactly what to do when the Copilot bridge is not answering.
//
// "Not installed", "installed but VS Code has not loaded it" and "VS Code is
// closed" need three different fixes, and guessing between them wastes the
// user's time. The banner re-checks itself and disappears on its own, so there
// is nothing to press once the situation is resolved.

import { api } from "./api.js";
import { banner, dismissBanner } from "./notify.js";

const KEY = "bridge";
let timer = null;
let dismissedUntil = 0;

export function startBridgeWatch(getState) {
  const check = async () => {
    let state;
    try {
      state = await api.state();
    } catch {
      return;
    }
    getState?.(state);
    evaluate(state);
  };
  check();
  timer = setInterval(check, 6000);
  return () => clearInterval(timer);
}

function evaluate(state) {
  const provider = state.provider || {};
  const bridge = state.bridge || {};

  if (provider.available) {
    dismissBanner(KEY);
    return;
  }
  if (Date.now() < dismissedUntil) return;

  if (provider.key !== "vscode") {
    banner(KEY, {
      kind: "danger",
      title: `${provider.label || "The language model"} is not available`,
      body: provider.detail || "Open Settings to choose a working provider.",
      actions: [{ label: "Open settings", run: () => (location.hash = "#/settings") }],
    });
    return;
  }

  if (!bridge.extension_installed) {
    banner(KEY, {
      kind: "danger",
      title: "The JobLookup bridge is not installed in VS Code",
      body: "Run .\\scripts\\install-bridge.ps1 from the JobLookup folder, then reload VS Code.",
      actions: [{ label: "How to fix", run: () => (location.hash = "#/settings") }],
    });
    return;
  }

  if (!bridge.handshake_present) {
    banner(KEY, {
      kind: "warning",
      title: "VS Code has not loaded the bridge yet",
      body: "Switch to VS Code, press Ctrl+Shift+P and run 'Developer: Reload Window'. Keep that window open while JobLookup is scoring.",
      actions: [],
    });
    return;
  }

  banner(KEY, {
    kind: "warning",
    title: "The bridge is running but Copilot has not been authorised",
    body: "In VS Code, press Ctrl+Shift+P and run 'JobLookup Bridge: Authorise Copilot Access'. Accept the permission dialog when it appears.",
    actions: [],
  });
}

/** Suppress the banner for a while — used when the user chooses to carry on. */
export function snoozeBridgeBanner(minutes = 10) {
  dismissedUntil = Date.now() + minutes * 60_000;
  dismissBanner(KEY);
}
