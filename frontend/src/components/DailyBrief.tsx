import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, Download, Inbox } from "lucide-react";
import { Link } from "react-router-dom";
import { request } from "../api";
import type { NextAction } from "../types";
import { Dialog, ErrorState, Spinner } from "./ui";

type Brief = {
  track_name: string;
  unseen_count: number;
  recommended_count: number;
  review_count: number;
  items: {
    id: number;
    title: string;
    company: string;
    score: number;
    band: string;
    state: string;
  }[];
  actions: (NextAction & { overdue: boolean })[];
};

export function DailyBrief({ trackId }: { trackId: number }) {
  const [open, setOpen] = useState(false);
  const brief = useQuery({
    queryKey: ["digest", trackId],
    queryFn: ({ signal }) =>
      request<Brief>(`/digest?track_id=${trackId}`, { signal }),
    enabled: open,
    staleTime: 0,
  });
  return (
    <>
      <button className="button secondary small" onClick={() => setOpen(true)}>
        <Inbox size={15} />
        Daily brief
      </button>
      {open && (
        <Dialog title="Daily brief" onClose={() => setOpen(false)}>
          <div className="dialog-body workflow-form">
            {brief.isPending ? (
              <Spinner />
            ) : brief.isError ? (
              <ErrorState
                error={brief.error}
                retry={() => void brief.refetch()}
              />
            ) : (
              <>
                <h2>{brief.data.track_name}</h2>
                <div className="workflow-stat-strip">
                  <div>
                    <strong>{brief.data.recommended_count}</strong>
                    <span>Unseen recommendations</span>
                  </div>
                  <div>
                    <strong>{brief.data.review_count}</strong>
                    <span>Need review</span>
                  </div>
                  <div>
                    <strong>{brief.data.actions.length}</strong>
                    <span>Actions this week</span>
                  </div>
                </div>
                <h3>Next opportunities</h3>
                {brief.data.items.length ? (
                  brief.data.items.map((item) => (
                    <div className="brief-opportunity" key={item.id}>
                      <Link
                        to={`/matches?view=all&track=${trackId}&job=${item.id}`}
                        onClick={() => setOpen(false)}
                      >
                        {item.title}
                      </Link>
                      <p>
                        {item.company} / {item.score} fit /{" "}
                        {item.band === "review"
                          ? "Needs review"
                          : item.state === "changed"
                            ? "Updated posting"
                            : "New posting"}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="muted">No unseen opportunities.</p>
                )}
                <h3>
                  <CalendarClock size={16} />
                  Due this week
                </h3>
                {brief.data.actions.length ? (
                  brief.data.actions.map((item) => (
                    <div key={item.id} className="brief-opportunity">
                      <Link to="/applications" onClick={() => setOpen(false)}>
                        {item.title}
                      </Link>
                      <p className={item.overdue ? "error-text" : "muted"}>
                        {item.company} /{" "}
                        {new Date(item.due_at).toLocaleString()}
                        {item.overdue ? " / Overdue" : ""}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="muted">No upcoming actions.</p>
                )}
              </>
            )}
          </div>
          <footer className="dialog-footer">
            <a
              className="button secondary"
              href={`/api/digest/export?track_id=${trackId}`}
            >
              <Download size={15} />
              Download brief
            </a>
            <button className="button primary" onClick={() => setOpen(false)}>
              Done
            </button>
          </footer>
        </Dialog>
      )}
    </>
  );
}
