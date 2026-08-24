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
      onDismiss: snooze,
      title: `${provider.label || "The language model"} is not available`,
      body: provider.detail || "Open Settings to choose a working provider.",
      actions: [{ label: "Open settings", run: () => (location.hash = "#/settings") }],
    });
    return;
  }

  if (!bridge.extension_installed) {
    banner(KEY, {
      kind: "danger",
      onDismiss: snooze,
      title: "The JobLookup bridge is not installed in VS Code",
      body: "Run .\\scripts\\install-bridge.ps1 from the JobLookup folder, then reload VS Code.",
      actions: [otherModel],
    });
    return;
  }

  if (!bridge.handshake_present) {
    banner(KEY, {
      kind: "warning",
      onDismiss: snooze,
      title: "VS Code has not loaded the bridge yet",
      body: "Switch to VS Code, press Ctrl+Shift+P and run 'Developer: Reload Window'. Keep that window open while JobLookup is scoring.",
      actions: [otherModel],
    });
    return;
  }

  banner(KEY, {
    kind: "warning",
    onDismiss: snooze,
    title: "The bridge is running but Copilot has not been authorised",
    body: "In VS Code, press Ctrl+Shift+P and run 'JobLookup Bridge: Authorise Copilot Access'. Accept the permission dialog when it appears.",
    actions: [otherModel],
  });
}

//: Every one of these banners is a reason the bridge cannot be used, and the
//: bridge is not the only way to get a model. Saying so beats leaving the user
//: with an instruction they may not be able to follow.
const otherModel = {
  label: "Use another model",
  run: () => (location.hash = "#/settings"),
};

/**
 * Stop nagging for a while.
 *
 * The check runs every six seconds, so simply removing the banner would put it
 * straight back. Dismiss has to mean "I know, leave me alone", not "redraw".
 */
function snooze(minutes = 10) {
  dismissedUntil = Date.now() + minutes * 60_000;
  dismissBanner(KEY);
}
