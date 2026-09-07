import { useDeferredValue, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  Download,
  MessageSquare,
  Search,
  Trash2,
} from "lucide-react";
import { errorMessage, post, refreshWorkspace, request } from "../api";
import { ago, companyColor, initials, safeLink, STAGES } from "../lib/format";
import type { Application } from "../types";
import { JobDetails } from "../components/JobDetails";
import {
  Confirm,
  Dialog,
  EmptyState,
  ErrorState,
  IconButton,
  PageHead,
  Spinner,
} from "../components/ui";
import { useToast } from "../components/notifications";

export default function Applications() {
  const [query, setQuery] = useState("");
  const [stage, setStage] = useState("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [clearOpen, setClearOpen] = useState(false);
  const deferredQuery = useDeferredValue(query);
  const notify = useToast();
  const applications = useQuery({
    queryKey: ["applications"],
    queryFn: ({ signal }) =>
      request<{ applications: Application[]; statuses: string[] }>(
        "/applications",
        { signal },
      ),
  });
  const entries = applications.data?.applications || [];
  const displayed = entries.filter(
    (entry) =>
      (stage === "all" || entry.status === stage) &&
      `${entry.title} ${entry.company}`
        .toLowerCase()
        .includes(deferredQuery.toLowerCase()),
  );
  const active = entries.filter(
    (entry) => !["rejected", "withdrawn"].includes(entry.status),
  ).length;
  return (
    <>
      <PageHead
        eyebrow="MAKE YOUR NEXT MOVE"
        title="Applications"
        detail={`${entries.length} tracked roles. ${active} active opportunities.`}
      >
        <button
          className="button secondary"
          disabled={!entries.length}
          onClick={() => exportApplications(entries)}
        >
          <Download size={16} />
          Export
        </button>
        <IconButton
          label="Clear application list"
          disabled={!entries.length}
          onClick={() => setClearOpen(true)}
        >
          <Trash2 size={18} />
        </IconButton>
      </PageHead>
      <div className="application-stages" aria-label="Application stages">
        {Object.entries(STAGES).map(([key, name]) => (
          <button
            key={key}
            className={stage === key ? `active stage-${key}` : ""}
            onClick={() => setStage(stage === key ? "all" : key)}
            aria-pressed={stage === key}
          >
            <span className={`stage-dot stage-${key}`} />
            <span>{name}</span>
            <strong>
              {entries.filter((entry) => entry.status === key).length}
            </strong>
          </button>
        ))}
      </div>
      <div className="results-toolbar application-toolbar">
        <div className="search-input">
          <Search size={17} />
          <input
            aria-label="Search applications"
            placeholder="Search your applications"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <select
          aria-label="Filter application stage"
          value={stage}
          onChange={(event) => setStage(event.target.value)}
        >
          <option value="all">All stages</option>
          {Object.entries(STAGES).map(([key, name]) => (
            <option value={key} key={key}>
              {name}
            </option>
          ))}
        </select>
        <span className="result-count">{displayed.length} roles</span>
      </div>
      {applications.isPending ? (
        <div className="detail-loading">
          <Spinner />
        </div>
      ) : applications.isError ? (
        <ErrorState
          error={applications.error}
          retry={() => void applications.refetch()}
        />
      ) : displayed.length ? (
        <div className="application-list">
          <div className="application-table-head">
            <span>Opportunity</span>
            <span>Stage</span>
            <span>Updated</span>
            <span>Actions</span>
          </div>
          {displayed.map((entry) => (
            <ApplicationRow
              key={entry.job_id}
              entry={entry}
              onOpen={() => setSelectedId(entry.job_id)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title={
            entries.length
              ? "No applications in this view"
              : "A little closer to your next role"
          }
          detail={
            entries.length
              ? "No tracked roles match these filters."
              : "Your application list is empty."
          }
        >
          <Link className="button primary" to="/matches">
            Explore matches
            <ArrowRight size={16} />
          </Link>
        </EmptyState>
      )}
      {selectedId != null && (
        <JobDetails id={selectedId} onClose={() => setSelectedId(null)} />
      )}
      {clearOpen && (
        <Confirm
          title="Clear all applications?"
          detail="This removes your application statuses and notes. The original job postings, resumes, and profile will be kept."
          action="Clear applications"
          onClose={() => setClearOpen(false)}
          onConfirm={async () => {
            await request("/applications", { method: "DELETE" });
            await refreshWorkspace();
            notify("Application list cleared.");
          }}
        />
      )}
    </>
  );
}

function ApplicationRow({
  entry,
  onOpen,
}: {
  entry: Application;
  onOpen: () => void;
}) {
  const [removeOpen, setRemoveOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [notes, setNotes] = useState(entry.notes || "");
  const notify = useToast();
  const update = useMutation({
    mutationFn: (changes: { status: string; notes?: string }) =>
      post(`/jobs/${entry.job_id}/application`, changes),
    onSuccess: async () => {
      setNotesOpen(false);
      notify("Application updated.");
      await refreshWorkspace();
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  return (
    <>
      <article className="application-row">
        <div className="application-role">
          <div
            className={`company-avatar small-avatar color-${companyColor(entry.company)}`}
          >
            {initials(entry.company)}
          </div>
          <div>
            <button className="text-title" onClick={onOpen}>
              {entry.title}
            </button>
            <p>{entry.company}</p>
          </div>
        </div>
        <select
          className={`stage-picker stage-${entry.status}`}
          aria-label={`Stage for ${entry.title}`}
          value={entry.status}
          disabled={update.isPending}
          onChange={(event) => update.mutate({ status: event.target.value })}
        >
          {Object.entries(STAGES).map(([key, name]) => (
            <option value={key} key={key}>
              {name}
            </option>
          ))}
        </select>
        <span className="updated-date">{ago(entry.updated_at)}</span>
        <div className="application-actions">
          <IconButton
            label={`Notes for ${entry.title}`}
            className={entry.notes ? "has-notes" : ""}
            onClick={() => {
              setNotes(entry.notes || "");
              setNotesOpen(true);
            }}
          >
            <MessageSquare size={16} />
          </IconButton>
          {safeLink(entry.url) && (
            <a
              className="icon-button"
              aria-label={`Original posting for ${entry.title}`}
              title="Original posting"
              href={safeLink(entry.url)}
              target="_blank"
              rel="noreferrer noopener"
            >
              <ArrowUpRight size={16} />
            </a>
          )}
          <IconButton
            label={`Remove ${entry.title}`}
            onClick={() => setRemoveOpen(true)}
          >
            <Trash2 size={16} />
          </IconButton>
        </div>
      </article>
      {removeOpen && (
        <Confirm
          title="Remove this application?"
          detail={`${entry.title} at ${entry.company} will be removed from your tracking list. The job posting stays in Matches.`}
          action="Remove application"
          onClose={() => setRemoveOpen(false)}
          onConfirm={async () => {
            await request(`/jobs/${entry.job_id}/application`, {
              method: "DELETE",
            });
            await refreshWorkspace();
            notify("Application removed.");
          }}
        />
      )}
      {notesOpen && (
        <Dialog title="Application notes" onClose={() => setNotesOpen(false)}>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              update.mutate({ status: entry.status, notes });
            }}
          >
            <div className="dialog-body">
              <p className="notes-context">
                {entry.title}
                <span>{entry.company}</span>
              </p>
              <label className="sr-only" htmlFor="application-notes">
                Notes
              </label>
              <textarea
                id="application-notes"
                autoFocus
                rows={7}
                maxLength={10000}
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Recruiter details, interview dates, next steps..."
              />
            </div>
            <footer className="dialog-footer">
              <button
                type="button"
                className="button secondary"
                onClick={() => setNotesOpen(false)}
              >
                Cancel
              </button>
              <button className="button primary" disabled={update.isPending}>
                {update.isPending && <Spinner />}Save notes
              </button>
            </footer>
          </form>
        </Dialog>
      )}
    </>
  );
}

function exportApplications(entries: Application[]) {
  const escape = (value: string) =>
    `"${(/^[=+\-@\t\r]/.test(value) ? "'" + value : value).replaceAll('"', '""')}"`;
  const rows = [
    ["Role", "Company", "Stage", "Updated", "Notes", "URL"],
    ...entries.map((entry) => [
      entry.title,
      entry.company,
      STAGES[entry.status] || entry.status,
      entry.updated_at,
      entry.notes || "",
      safeLink(entry.url),
    ]),
  ];
  const url = URL.createObjectURL(
    new Blob([rows.map((row) => row.map(escape).join(",")).join("\r\n")], {
      type: "text/csv;charset=utf-8",
    }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "joblookup-applications.csv";
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
