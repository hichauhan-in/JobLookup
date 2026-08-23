// Tiny DOM helpers. No framework, no build step, no virtual DOM — the screens
// here are small enough that re-rendering a section by hand is simpler to read
// than any abstraction over it.
//
// The layout primitives below (card, settingRow, rows, toggle) exist so every
// screen lays out the same way. A one-off flex container inside a view is how a
// UI drifts into looking assembled rather than designed.

export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "html") node.innerHTML = value;
    else if (key === "text") node.textContent = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "style" && typeof value === "object") Object.assign(node.style, value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  append(node, children);
  return node;
}

function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

export function mount(node, ...children) {
  clear(node);
  append(node, children);
  return node;
}

// --- controls ----------------------------------------------------------------

/** A spinning ring, for whenever something is genuinely in flight. */
export function spinner(size = 20) {
  return el("span", {
    class: "spinner",
    role: "status",
    "aria-label": "Loading",
    style: { width: `${size}px`, height: `${size}px` },
  });
}

/** One big number with its caption. The unit every summary strip is built from. */
export function stat(value, label) {
  return el(
    "div",
    { class: "stat" },
    el("div", { class: "value", text: String(value ?? 0) }),
    el("div", { class: "label", text: label })
  );
}

/** A grey bar standing in for content that has not arrived yet. */
export function skeleton(modifier = "") {
  return el("div", { class: `skeleton${modifier ? ` ${modifier}` : ""}` });
}

/**
 * An on/off switch.
 *
 * A checkbox is a 13px hit target whose state you have to squint at. This is the
 * same semantics with a target you can actually hit and a state readable at a
 * glance. It exposes `.checked` and `.disabled` directly, so it drops into any
 * place a checkbox used to sit.
 */
export function toggle(checked = false, { onChange, disabled = false, title = "", label = "" } = {}) {
  const input = el("input", { type: "checkbox", checked, disabled, role: "switch" });
  if (label) input.setAttribute("aria-label", label);

  const node = el(
    "label",
    { class: `switch${disabled ? " is-disabled" : ""}`, title },
    input,
    el("span", { class: "switch-track" }, el("i", { class: "switch-knob" }))
  );

  if (onChange) input.addEventListener("change", () => onChange(input.checked));

  Object.defineProperty(node, "checked", {
    get: () => input.checked,
    set: (value) => {
      input.checked = Boolean(value);
    },
  });
  Object.defineProperty(node, "disabled", {
    get: () => input.disabled,
    set: (value) => {
      input.disabled = Boolean(value);
      node.classList.toggle("is-disabled", Boolean(value));
    },
  });
  node.input = input;
  return node;
}

/** A single-select choice: one of these, not several. Returns `.value`. */export function chipGroup(options, value, onChange) {
  const node = el("div", { class: "chip-group", role: "radiogroup" });
  let current = value;
  const buttons = options.map(([optionValue, label, title]) => {
    const button = el("button", {
      type: "button",
      class: `chip-toggle${optionValue === current ? " is-on" : ""}`,
      role: "radio",
      "aria-checked": optionValue === current ? "true" : "false",
      title: title || "",
      text: label,
    });
    button.addEventListener("click", () => {
      current = optionValue;
      node.value = current;
      for (const other of buttons) {
        const on = other === button;
        other.classList.toggle("is-on", on);
        other.setAttribute("aria-checked", on ? "true" : "false");
      }
      onChange?.(current);
    });
    return button;
  });
  node.append(...buttons);
  node.value = current;
  return node;
}

/** A multi-select choice. Bigger than a checkbox, and reads as a set rather than a list. */
export function chipToggle(label, selected, onChange) {
  const node = el("button", {
    type: "button",
    class: `chip-toggle${selected ? " is-on" : ""}`,
    "aria-pressed": selected ? "true" : "false",
    text: label,
  });
  node.addEventListener("click", () => {
    const next = node.classList.toggle("is-on");
    node.setAttribute("aria-pressed", next ? "true" : "false");
    onChange(next);
  });
  return node;
}

// --- layout ------------------------------------------------------------------

/** A titled panel. `actions` sits opposite the title. */
export function card({ title = "", subtitle = "", actions = null, tone = "" } = {}, ...children) {
  const head =
    title || subtitle || actions
      ? el(
          "header",
          { class: "card-head" },
          el(
            "div",
            { class: "card-heading" },
            title && el("h2", { text: title }),
            subtitle && el("p", { class: "card-sub", text: subtitle })
          ),
          actions && el("div", { class: "card-actions" }, actions)
        )
      : null;
  return el(
    "section",
    { class: `card${tone ? ` card-${tone}` : ""}` },
    head,
    el("div", { class: "card-body" }, ...children)
  );
}

/** A collapsible panel that matches `card` when open. */
export function accordion({ title, subtitle = "", badge = null, open = false } = {}, ...children) {
  return el(
    "details",
    { class: "card accordion", open },
    el(
      "summary",
      {},
      el(
        "div",
        { class: "card-heading" },
        el("h2", { text: title }),
        subtitle && el("p", { class: "card-sub", text: subtitle })
      ),
      badge
    ),
    el("div", { class: "card-body" }, ...children)
  );
}

/** One labelled setting: name and explanation on the left, control on the right. */
export function settingRow(label, control, help, { wide = false } = {}) {
  return el(
    "div",
    { class: `setting${wide ? " setting-wide" : ""}` },
    el(
      "div",
      { class: "setting-label" },
      el("span", { class: "setting-title", text: label }),
      help && el("span", { class: "setting-help", text: help })
    ),
    el("div", { class: "setting-control" }, control)
  );
}

/** A divided list. Rows sit apart without each one needing its own border. */
export function rows(...children) {
  return el("div", { class: "rows" }, ...children);
}

/** The same list, but it flows into extra columns when the window is wide. */
export function splitRows(...children) {
  return el("div", { class: "rows split" }, ...children);
}

/** A small round "?" that opens an explanation. */
export function helpButton(label, onOpen) {
  return el("button", {
    type: "button",
    class: "help-button",
    title: label,
    "aria-label": label,
    onClick: (event) => {
      event.stopPropagation();
      onOpen();
    },
  }, "?");
}

/**
 * A modal explanation. Returns its own close function.
 *
 * Closes on Escape, on the backdrop, and on the button, because a dialog you
 * cannot get out of is worse than no dialog.
 */
export function openDialog({ title, subtitle = "" } = {}, ...children) {
  const close = () => {
    overlay.remove();
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (event) => {
    if (event.key === "Escape") close();
  };

  const closeButton = el("button", { class: "ghost small", onClick: close }, "Close");
  const panel = el(
    "div",
    { class: "dialog", role: "dialog", "aria-modal": "true", "aria-label": title },
    el(
      "header",
      { class: "dialog-head" },
      el(
        "div",
        { class: "card-heading" },
        el("h2", { text: title }),
        subtitle && el("p", { class: "card-sub", text: subtitle })
      ),
      closeButton
    ),
    el("div", { class: "dialog-body" }, ...children)
  );

  const overlay = el(
    "div",
    {
      class: "dialog-overlay",
      onClick: (event) => {
        if (event.target === overlay) close();
      },
    },
    panel
  );

  document.body.append(overlay);
  document.addEventListener("keydown", onKey);
  closeButton.focus();
  return close;
}

export function field(label, control, help) {
  return el(
    "div",
    { class: "field" },
    el("label", { text: label }),
    control,
    help && el("div", { class: "field-help", text: help })
  );
}

/** A textarea that reads and writes a comma or newline separated list. */
export function listInput(value, placeholder) {
  return el("textarea", {
    value: (value || []).join(", "),
    placeholder: placeholder || "",
    rows: 2,
  });
}

export function readList(node) {
  return node.value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
