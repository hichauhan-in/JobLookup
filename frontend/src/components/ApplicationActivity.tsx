import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  Circle,
  Plus,
  RotateCcw,
  Save,
  Trash2,
} from "lucide-react";
import { errorMessage, post, refreshWorkspace, request } from "../api";
import type { Application, NextAction, ResumeVersion } from "../types";
import { dateLabel, STAGES } from "../lib/format";
import { Dialog, ErrorState, Field, IconButton, Spinner } from "./ui";
import { useToast } from "./notifications";

type Activity = {
  application: Application & {
    contact_name: string;
    contact_email: string;
    submitted_version_id: number | null;
  };
  events: { id: number; kind: string; detail: string; created_at: string }[];
  tasks: NextAction[];
  versions: ResumeVersion[];
};

export function Agenda({ onOpen }: { onOpen: (jobId: number) => void }) {
  const [all, setAll] = useState(false);
  const notify = useToast();
  const agenda = useQuery({
    queryKey: ["agenda"],
    queryFn: async ({ signal }) => {
      const response = await request<{ items: NextAction[] }>("/agenda", { signal });
      const now = Date.now();
      return { items: response.items.map((item) => ({ ...item, overdue: new Date(item.due_at).getTime() < now })) };
    },
    refetchInterval: 60_000,
  });
  const complete = useMutation({
    mutationFn: (id: number) =>
      request(`/actions/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ done: true }),
      }),
    onSuccess: () => refreshWorkspace(),
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const items = agenda.data?.items || [];
  return (
    <section className="agenda-section" aria-label="Next actions">
      <div className="section-title">
        <h2>
          <CalendarClock size={18} />
          Next actions <span className="count-badge">{items.length}</span>
        </h2>
        {items.length > 5 && (
          <button className="text-button" onClick={() => setAll(!all)}>
            {all ? "Show less" : "Show all"}
          </button>
        )}
      </div>
      {agenda.isError ? (
        <ErrorState error={agenda.error} retry={() => void agenda.refetch()} />
      ) : agenda.isPending ? (
        <Spinner />
      ) : items.length ? (
        (all ? items : items.slice(0, 5)).map((item) => (
          <div
            className={`agenda-row ${item.overdue ? "overdue" : ""}`}
            key={item.id}
          >
            <IconButton
              label={`Complete ${item.title}`}
              disabled={complete.isPending}
              onClick={() => complete.mutate(item.id)}
            >
              <Circle size={19} />
            </IconButton>
            <div>
              <button
                className="text-title"
                onClick={() => onOpen(item.job_id)}
              >
                {item.title}
              </button>
              <p>
                {item.company} / {item.job_title}
              </p>
            </div>
            <time dateTime={item.due_at}>
              {new Date(item.due_at).toLocaleString([], {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </time>
          </div>
        ))
      ) : (
        <p className="muted">No upcoming actions.</p>
      )}
    </section>
  );
}

export function ApplicationActivity({
  jobId,
  onClose,
}: {
  jobId: number;
  onClose: () => void;
}) {
  const activity = useQuery({
    queryKey: ["activity", jobId],
    queryFn: ({ signal }) =>
      request<Activity>(`/applications/${jobId}/activity`, { signal }),
  });
  return (
    <Dialog title="Application activity" drawer onClose={onClose}>
      <div className="dialog-body">
        {activity.isPending ? (
          <Spinner />
        ) : activity.isError ? (
          <ErrorState
            error={activity.error}
            retry={() => void activity.refetch()}
          />
        ) : (
          <ActivityEditor jobId={jobId} data={activity.data} />
        )}
      </div>
    </Dialog>
  );
}

function ActivityEditor({ jobId, data }: { jobId: number; data: Activity }) {
  const [contact, setContact] = useState({
    contact_name: data.application.contact_name || "",
    contact_email: data.application.contact_email || "",
    submitted_version_id: data.application.submitted_version_id,
  });
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [kind, setKind] = useState("followup");
  const notify = useToast();
  const save = useMutation({
    mutationFn: () =>
      request(`/applications/${jobId}/contact`, {
        method: "PUT",
        body: JSON.stringify(contact),
      }),
    onSuccess: async () => {
      await refreshWorkspace();
      notify("Application details saved.");
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const add = useMutation({
    mutationFn: () =>
      post(`/applications/${jobId}/actions`, {
        title,
        kind,
        due_at: new Date(due).toISOString(),
      }),
    onSuccess: async () => {
      setTitle("");
      setDue("");
      await refreshWorkspace();
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const change = useMutation({
    mutationFn: ({
      id,
      done,
      remove,
    }: {
      id: number;
      done?: boolean;
      remove?: boolean;
    }) =>
      request(`/actions/${id}`, {
        method: remove ? "DELETE" : "PATCH",
        body: remove ? undefined : JSON.stringify({ done }),
      }),
    onSuccess: () => refreshWorkspace(),
    onError: (error) => notify(errorMessage(error), "error"),
  });
  return (
    <div className="workflow-form">
      <h2>{STAGES[data.application.status] || data.application.status}</h2>
      <section className="workflow-section">
        <h3>Recruiter & submitted resume</h3>
        <form
          className="workflow-form"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <div className="form-grid">
            <Field id="contact-name" label="Recruiter name" optional>
              <input
                id="contact-name"
                maxLength={200}
                value={contact.contact_name}
                onChange={(event) =>
                  setContact({ ...contact, contact_name: event.target.value })
                }
              />
            </Field>
            <Field id="contact-email" label="Recruiter email" optional>
              <input
                id="contact-email"
                type="email"
                maxLength={320}
                value={contact.contact_email}
                onChange={(event) =>
                  setContact({ ...contact, contact_email: event.target.value })
                }
              />
            </Field>
          </div>
          <Field id="submitted-version" label="Resume submitted">
            <select
              id="submitted-version"
              value={contact.submitted_version_id || ""}
              onChange={(event) =>
                setContact({
                  ...contact,
                  submitted_version_id: Number(event.target.value) || null,
                })
              }
            >
              <option value="">Not recorded</option>
              {data.versions.map((version) => (
                <option key={version.id} value={version.id}>
                  Version {version.id} /{" "}
                  {version.cv_label || "Original removed"} /{" "}
                  {dateLabel(version.created_at)}
                </option>
              ))}
            </select>
          </Field>
          <div className="button-row">
            <button
              className="button secondary small"
              disabled={save.isPending}
            >
              {save.isPending ? <Spinner /> : <Save size={15} />}Save details
            </button>
            {contact.submitted_version_id && (
              <a
                href={`/api/resume-versions/${contact.submitted_version_id}/download`}
                className="text-button"
              >
                Download submitted version
              </a>
            )}
          </div>
        </form>
      </section>
      <section className="workflow-section">
        <h3>Next actions</h3>
        {data.tasks.map((task) => (
          <div
            className={`agenda-row ${task.done_at ? "is-complete" : ""}`}
            key={task.id}
          >
            <IconButton
              label={`${task.done_at ? "Reopen" : "Complete"} ${task.title}`}
              disabled={change.isPending}
              onClick={() =>
                change.mutate({ id: task.id, done: !task.done_at })
              }
            >
              {task.done_at ? <RotateCcw size={16} /> : <Check size={16} />}
            </IconButton>
            <div>
              <strong>{task.title}</strong>
              <p>{new Date(task.due_at).toLocaleString()}</p>
            </div>
            <IconButton
              label={`Delete ${task.title}`}
              disabled={change.isPending}
              onClick={() => change.mutate({ id: task.id, remove: true })}
            >
              <Trash2 size={15} />
            </IconButton>
          </div>
        ))}
        <form
          className="workflow-form"
          onSubmit={(event) => {
            event.preventDefault();
            add.mutate();
          }}
        >
          <Field id="action-title" label="Next action">
            <input
              id="action-title"
              required
              maxLength={200}
              placeholder="Follow up with recruiter"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </Field>
          <div className="form-grid">
            <Field id="action-kind" label="Action type">
              <select
                id="action-kind"
                value={kind}
                onChange={(event) => setKind(event.target.value)}
              >
                <option value="followup">Follow-up</option>
                <option value="interview">Interview</option>
                <option value="deadline">Deadline</option>
              </select>
            </Field>
            <Field id="action-due" label="Due at (local time)">
              <input
                id="action-due"
                type="datetime-local"
                required
                value={due}
                onChange={(event) => setDue(event.target.value)}
              />
            </Field>
          </div>
          <button
            className="button secondary small align-start"
            disabled={add.isPending || !title.trim() || !due}
          >
            {add.isPending ? <Spinner /> : <Plus size={15} />}Add next action
          </button>
        </form>
      </section>
      <section className="workflow-section">
        <h3>Timeline</h3>
        <ol className="activity-timeline">
          {data.events.map((event) => (
            <li key={event.id}>
              <span>{dateLabel(event.created_at)}</span>
              <p>{event.detail}</p>
            </li>
          ))}
        </ol>
        {!data.events.length && (
          <p className="muted">No recorded activity yet.</p>
        )}
      </section>
    </div>
  );
}
