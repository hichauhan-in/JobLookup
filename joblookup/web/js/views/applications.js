// Where every application you are tracking stands.

import { api } from "../api.js";
import { app } from "../app.js";
import { card, el, mount } from "../dom.js";
import { bandLabel, relativeDate } from "../format.js";

const ORDER = ["offer", "interviewing", "applied", "saved", "rejected"];

export async function renderApplications(container) {
  const { applications } = await api.applications();

  if (!applications.length) {
    mount(container,
      el("div", { class: "page-head" }, el("h1", { text: "Applications" })),
      card({},
        el("div", { class: "empty" },
          el("p", { text: "Nothing tracked yet." }),
          el("p", { class: "small-text", text: "Open a match and set its status to start following it." }),
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

  mount(container,
    el("div", { class: "page-head" },
      el("h1", { text: "Applications" }),
      el("p", { text: `${applications.length} tracked. Statuses are set from a posting's own screen.` })
    ),
    el("div", { class: "stack" },
      el("div", { class: "grid four" },
        ...ORDER.map((status) =>
          el("div", { class: "stat" },
            el("div", { class: "value", text: String((grouped.get(status) || []).length) }),
            el("div", { class: "label", text: status })
          )
        )
      ),
      ...ORDER.filter((status) => (grouped.get(status) || []).length).map((status) =>
        card(
          { title: status, actions: el("span", { class: "chip", text: String(grouped.get(status).length) }) },
          el("table", {},
            el("thead", {}, el("tr", {},
              el("th", { text: "Role" }), el("th", { text: "Company" }),
              el("th", { text: "Fit" }), el("th", { text: "Updated" }), el("th", {})
            )),
            el("tbody", {},
              ...grouped.get(status).map((entry) =>
                el("tr", {},
                  el("td", { text: entry.title }),
                  el("td", { class: "muted", text: entry.company }),
                  el("td", {}, el("span", { class: `band band-${entry.band || "rejected"}`, text: bandLabel(entry.band) })),
                  el("td", { class: "muted small-text", text: relativeDate(`${(entry.updated_at || "").replace(" ", "T")}Z`) }),
                  el("td", {}, el("button", { class: "link small", onClick: () => app.go(`/job/${entry.job_id}`) }, "Open"))
                )
              )
            )
          )
        )
      )
    )
  );
}
