// Transient messages and the persistent banner at the top of the window.

import { el, clear } from "./dom.js";

const toasts = () => document.getElementById("toasts");
const alerts = () => document.getElementById("alerts");

export function toast(message, kind = "info", timeout = 5200) {
  const node = el("div", { class: `toast ${kind}`, text: message });
  toasts().append(node);
  setTimeout(() => node.remove(), timeout);
  return node;
}

export const ok = (message) => toast(message, "ok");
export const warn = (message) => toast(message, "warn", 8000);
export const fail = (message) => toast(message, "error", 12000);

const banners = new Map();

/**
 * A banner that stays until the situation it describes is resolved.
 *
 * Keyed, so the same condition re-reported does not stack up — the bridge check
 * runs every few seconds and would otherwise paper the screen.
 *
 * `onDismiss` matters more than it looks. A banner raised by a repeating check
 * is re-raised on the next tick, so removing the node is not dismissing it. The
 * caller has to be told, so it can stop asking for a while.
 */
export function banner(key, { title, body, actions = [], kind = "info", onDismiss } = {}) {
  let node = banners.get(key);
  if (!node) {
    node = el("div", { class: `notice ${kind}` });
    banners.set(key, node);
    alerts().append(node);
  }
  clear(node);
  node.className = `notice ${kind}`;
  node.append(
    el("div", { class: "row between" },
      el("div", {}, el("strong", { text: title }), body && el("div", { class: "small-text", text: body })),
      el("div", { class: "row" },
        ...actions.map((action) =>
          el("button", { class: "ghost small", onClick: action.run }, action.label)
        ),
        el("button", {
          class: "link small",
          onClick: () => (onDismiss ? onDismiss() : dismissBanner(key)),
        }, "Dismiss")
      )
    )
  );
  return node;
}

export function dismissBanner(key) {
  const node = banners.get(key);
  if (node) {
    node.remove();
    banners.delete(key);
  }
}
