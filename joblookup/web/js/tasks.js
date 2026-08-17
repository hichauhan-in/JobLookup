// Watching a background task: a progress card, a live log, and a promise that
// settles when the work finishes.
//
// The WebSocket replays everything that already happened when it connects, so
// navigating away and back mid-search does not lose the history.

import { api } from "./api.js";
import { clear, el } from "./dom.js";
import { fail } from "./notify.js";

const watchers = new Map();

export function activeTasks() {
  return [...watchers.values()].map((watcher) => watcher.task);
}

export class TaskView {
  constructor(task, { compact = false } = {}) {
    this.task = task;
    this.compact = compact;
    this.lines = [];
    this.log = el("div", { class: "task-log" });
    this.title = el("strong", { text: task.label || "Working" });
    this.status = el("span", { class: "muted small-text", text: "Queued" });
    this.fill = el("i", { style: { width: "0%" } });
    this.cancelButton = el(
      "button",
      { class: "link small", onClick: () => this.cancel() },
      "Stop"
    );
    this.node = el(
      "div",
      { class: "task" },
      el("div", { class: "row between" }, this.title, el("div", { class: "row" }, this.status, this.cancelButton)),
      el("div", { class: "bar" }, this.fill),
      compact ? null : this.log
    );
  }

  async cancel() {
    try {
      await api.cancelTask(this.task.id);
      this.status.textContent = "Stopping...";
    } catch (error) {
      fail(error.message);
    }
  }

  append(text, kind = "") {
    if (this.compact) return;
    this.lines.push(text);
    this.log.append(el("div", { class: kind, text }));
    this.log.scrollTop = this.log.scrollHeight;
  }

  apply(payload) {
    const summary = payload.job || this.task;
    this.task = summary;
    if (payload.type === "event") {
      const event = payload.event || {};
      if (event.fraction !== null && event.fraction !== undefined) {
        this.fill.style.width = `${Math.round(event.fraction * 100)}%`;
      }
      if (event.message) {
        this.status.textContent = event.message;
        const kind = event.type === "error" ? "err" : event.type === "warning" ? "warn" : "";
        this.append(event.message, kind);
      } else if (event.type === "stage_start" && event.stage) {
        this.append(`> ${event.stage}`);
      }
    } else if (payload.type === "done") {
      this.fill.style.width = "100%";
      this.cancelButton.remove();
      this.status.textContent =
        summary.status === "failed"
          ? summary.error || "Failed"
          : summary.status === "cancelled"
            ? "Stopped"
            : "Done";
      if (summary.status === "failed") this.append(summary.error || "Failed", "err");
    } else if (payload.type === "started") {
      this.status.textContent = "Running";
    }
  }
}

/**
 * Follow a task to completion.
 *
 * Falls back to polling if the WebSocket cannot be established, because a
 * corporate proxy occasionally blocks the upgrade and a search that silently
 * appears to hang is much worse than a slightly less smooth progress bar.
 */
export function watch(task, { view = null, onEvent = null } = {}) {
  return new Promise((resolve, reject) => {
    const record = { task, view };
    watchers.set(task.id, record);

    const finish = async (summary) => {
      watchers.delete(task.id);
      notifyChange();
      try {
        const latest = await api.task(task.id);
        if (latest.task.status === "failed") reject(new Error(latest.error || "The task failed."));
        else resolve(latest.result || {});
      } catch (error) {
        if (summary?.status === "failed") reject(new Error(summary.error || "The task failed."));
        else reject(error);
      }
    };

    let socket;
    try {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/ws/tasks/${task.id}`);
    } catch {
      poll(task, finish, reject);
      notifyChange();
      return;
    }

    let opened = false;
    socket.onopen = () => {
      opened = true;
      notifyChange();
    };
    socket.onmessage = (message) => {
      let payload;
      try {
        payload = JSON.parse(message.data);
      } catch {
        return;
      }
      record.task = payload.job || record.task;
      view?.apply(payload);
      onEvent?.(payload);
      notifyChange();
      if (payload.type === "done") {
        socket.close();
        finish(payload.job);
      }
    };
    socket.onerror = () => {
      if (!opened) poll(task, finish, reject);
    };
    socket.onclose = () => {
      if (watchers.has(task.id)) poll(task, finish, reject);
    };
  });
}

function poll(task, finish, reject) {
  const timer = setInterval(async () => {
    try {
      const latest = await api.task(task.id);
      if (!["queued", "running"].includes(latest.task.status)) {
        clearInterval(timer);
        finish(latest.task);
      }
    } catch (error) {
      clearInterval(timer);
      watchers.delete(task.id);
      reject(error);
    }
  }, 1500);
}

const listeners = new Set();

export function onTasksChanged(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notifyChange() {
  for (const listener of listeners) {
    try {
      listener(activeTasks());
    } catch {
      /* a broken listener must not stop the others */
    }
  }
}

export function renderTaskFooter(container) {
  const draw = (tasks) => {
    clear(container);
    for (const task of tasks) {
      container.append(
        el(
          "div",
          { class: "task" },
          el("div", { class: "row between" },
            el("span", { class: "small-text", text: task.label || task.kind }),
            el("span", { class: "muted small-text", text: task.status })
          ),
          el("div", { class: "bar" }, el("i", { style: { width: `${Math.round((task.fraction || 0) * 100)}%` } }))
        )
      );
    }
  };
  draw(activeTasks());
  return onTasksChanged(draw);
}
