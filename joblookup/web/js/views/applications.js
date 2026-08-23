// Where every application you are tracking stands, and the one place to move it
// along. Opening a posting to change one word of its status was a trip you
// should not have to make, so the status and the delete both live in the list.

import { api } from "../api.js";
import { app } from "../app.js";
import { card, el, mount, stat } from "../dom.js";
import { bandLabel, relativeDate, utc } from "../format.js";
import { fail, ok } from "../notify.js";

//: The order things actually happen in, which is also how they are grouped.
const ORDER = ["saved", "applied", "interviewing", "offer", "rejected"];

const LABELS = {
  saved: "Saved",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
};

const BLURB = {
  saved: "Worth a look, not sent yet.",
  applied: "Sent. Waiting to hear back.",
  interviewing: "In conversation with them.",
  offer: "They made you an offer.",
  rejected: "Closed, either way round.",
};

export async function renderApplications(container) {
  const payload = await api.applications();
  const applications = payload.applications || [];
  const statuses = payload.statuses?.length ? payload.statuses : ORDER;

  if (!applications.length) {
    mount(container,
      el("div", { class: "page-head" }, el("h1", { text: "Applications" })),
      card({},
        el("div", { class: "empty" },
          el("p", { text: "Nothing tracked yet." }),
          el("p", { class: "small-text", text: "Open a match and save it, and it will appear here to follow." }),
          el("div", { class: "row", style: { justifyContent: "center" } },
            el("button", { class: "ghost", onClick: () => app.go("/matches") }, "Go to matches")
          )
        )
      )
    );
    return;
  }

  const grouped = new Map(ORDER.map((status) => [status, []]));
  for (const entry of applications) {
    if (!grouped.has(entry.status)) grouped.set(entry.status, []);
    grouped.get(entry.status).push(entry);
  }

  const open = applications.filter((entry) => entry.status !== "rejected").length;

  mount(container,
    el("div", { class: "page-head" },
      el("h1", { text: "Applications" }),
      el("p", { text: `${applications.length} tracked, ${open} still live. Change a status or drop one without leaving this page.` })
    ),
    el("div", { class: "stack" },
      el("div", { class: "grid four" },
        ...ORDER.map((status) =>
          stat((grouped.get(status) || []).length, LABELS[status] || status)
        )
      ),
      ...ORDER.filter((status) => (grouped.get(status) || []).length).map((status) =>
        card(
          {
            title: LABELS[status] || status,
            subtitle: BLURB[status] || "",
            actions: el("span", { class: "chip", text: String(grouped.get(status).length) }),
          },
          el("table", { class: "applications" },
            el("thead", {}, el("tr", {},
              el("th", { text: "Role" }),
              el("th", { text: "Company" }),
              el("th", { text: "Fit" }),
              el("th", { text: "Updated" }),
              el("th", { text: "Status" }),
              el("th", {})
            )),
            el("tbody", {},
              ...grouped.get(status).map((entry) => row(entry, statuses, container))
            )
          )
        )
      )
    )
  );
}

function row(entry, statuses, container) {
  const picker = el("select", { class: "status-select", "aria-label": `Status for ${entry.title}` },
    ...statuses.map((status) =>
      el("option", { value: status, selected: status === entry.status }, LABELS[status] || status)
    )
  );
  picker.addEventListener("change", async () => {
    picker.disabled = true;
    try {
      await api.setApplication(entry.job_id, picker.value);
      ok(`${entry.title} is now ${(LABELS[picker.value] || picker.value).toLowerCase()}.`);
      await app.refreshState();
      await renderApplications(container);
    } catch (error) {
      fail(error.message);
      picker.value = entry.status;
      picker.disabled = false;
    }
  });

  const remove = el("button", {
    class: "ghost small danger",
    title: "Stop tracking this. The posting stays in your matches.",
    onClick: async () => {
      if (!confirm(`Stop tracking "${entry.title}" at ${entry.company}? The posting stays in your matches.`)) return;
      try {
        await api.deleteApplication(entry.job_id);
        ok("No longer tracking it.");
        await app.refreshState();
        await renderApplications(container);
      } catch (error) {
        fail(error.message);
      }
    },
  }, "Remove");

  return el("tr", {},
    el("td", {},
      el("button", { class: "link", onClick: () => app.go(`/job/${entry.job_id}`) }, entry.title || "Untitled")
    ),
    el("td", { class: "muted", text: entry.company || "" }),
    el("td", {},
      entry.band
        ? el("span", { class: `band band-${entry.band}`, text: bandLabel(entry.band) })
        : el("span", { class: "muted small-text", text: "not scored" })
    ),
    el("td", { class: "muted small-text", text: relativeDate(utc(entry.updated_at), "just now") }),
    el("td", {}, picker),
    el("td", {},
      el("div", { class: "row tight" },
        entry.url
          ? el("a", { class: "btn ghost small", href: entry.url, target: "_blank", rel: "noopener noreferrer" }, "Posting")
          : null,
        remove
      )
    )
  );
}
