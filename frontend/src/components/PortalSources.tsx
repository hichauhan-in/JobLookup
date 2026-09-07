import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  ArrowUpRight,
  Download,
  FilePlus2,
  Globe2,
  LogIn,
  LogOut,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import {
  errorMessage,
  post,
  queryClient,
  refreshWorkspace,
  request,
} from "../api";
import { safeLink } from "../lib/format";
import type { Portal, Portals, Task } from "../types";
import {
  Confirm,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  IconButton,
  Spinner,
} from "./ui";
import { useToast } from "./notifications";

async function refreshPortals() {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["portals"] }),
    queryClient.invalidateQueries({ queryKey: ["sources"] }),
    refreshWorkspace(),
  ]);
}

export function PortalSources({ query }: { query: string }) {
  const [setup, setSetup] = useState<Portal | null>(null);
  const [importing, setImporting] = useState<Portal | null>(null);
  const [disconnect, setDisconnect] = useState<Portal | null>(null);
  const [enableOpen, setEnableOpen] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const notify = useToast();
  const portals = useQuery({
    queryKey: ["portals"],
    queryFn: ({ signal }) => request<Portals>("/portals", { signal }),
  });
  const changeAccess = useMutation({
    mutationFn: (enabled: boolean) =>
      request("/portals", { method: "PUT", body: JSON.stringify({ enabled }) }),
    onSuccess: () => refreshPortals(),
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const task = useMutation({
    mutationFn: (path: string) => post<{ task: Task }>(path),
    onSuccess: async (result) => {
      setTaskId(result.task.id);
      await refreshWorkspace();
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const toggle = useMutation({
    mutationFn: (portal: Portal) =>
      request(`/portals/${portal.key}`, {
        method: "PUT",
        body: JSON.stringify({
          enabled: !portal.enabled,
          acknowledged: portal.risk_ack,
          access_mode: portal.access_mode,
          extra_terms: portal.config.extra_terms || [],
        }),
      }),
    onSuccess: () => refreshPortals(),
    onError: (error) => notify(errorMessage(error), "error"),
  });
  if (portals.isPending)
    return (
      <div className="detail-loading">
        <Spinner />
      </div>
    );
  if (portals.isError)
    return (
      <ErrorState error={portals.error} retry={() => void portals.refetch()} />
    );
  const data = portals.data;
  const visible = data.portals.filter((portal) =>
    portal.name.toLowerCase().includes(query.toLowerCase()),
  );
  if (!visible.length && query) return null;
  return (
    <section className="portal-section" aria-label="Job portals">
      <div className="section-title">
        <div>
          <h2>Job portals</h2>
          <p className="muted small">LinkedIn and other job sites</p>
        </div>
        <label className="portal-master-label">
          <span>Portal access</span>
          <span className="switch-control">
            <input
              type="checkbox"
              role="switch"
              aria-label="Enable portal access"
              checked={data.enabled}
              disabled={!data.local_only || changeAccess.isPending}
              onChange={(event) =>
                event.target.checked
                  ? setEnableOpen(true)
                  : changeAccess.mutate(false)
              }
            />
            <span />
          </span>
        </label>
      </div>
      <div className="portal-policy">
        <ShieldCheck size={18} />
        <p>
          Sign in on the portal's own page. Sessions stay on this device. Public
          access is best effort; account and verification restrictions still
          apply.
        </p>
      </div>
      {!data.local_only && (
        <p className="model-picker-status" role="status">
          Browser portal access is unavailable in a hosted workspace.
        </p>
      )}
      {data.enabled && !data.browser.browser_ready && (
        <div className="fact-notice warning">
          <AlertCircle size={18} />
          <div>
            <strong>Browser setup required for sign-in</strong>
            <p>{data.browser.detail}</p>
            <button
              className="button secondary small"
              disabled={task.isPending}
              onClick={() => task.mutate("/sources/playwright/install")}
            >
              <Download size={15} />
              Install browser support
            </button>
          </div>
        </div>
      )}
      {taskId && <PortalTask id={taskId} />}
      <div className="portal-list">
        {visible.map((portal) => (
          <article className="portal-row" key={portal.key}>
            <div className="portal-identity">
              <div className="source-icon blue">
                <Globe2 size={18} />
              </div>
              <div>
                <h3>{portal.name}</h3>
                <p>
                  {portal.access_mode === "public"
                    ? "Public listings · best effort"
                    : portal.session.authenticated
                      ? "Session verified · may expire"
                      : "Sign-in needed"}
                </p>
                {portal.enabled && !portal.ready && (
                  <p className="portal-status">{portal.blocked_reason}</p>
                )}
                {portal.last_error && (
                  <details className="portal-error">
                    <summary>Last access issue</summary>
                    <p>{portal.last_error}</p>
                  </details>
                )}
              </div>
              <label className="switch-control">
                <input
                  type="checkbox"
                  role="switch"
                  aria-label={`Include ${portal.name} in searches`}
                  checked={portal.enabled}
                  disabled={
                    !data.enabled || !data.local_only || toggle.isPending
                  }
                  onChange={() =>
                    !portal.enabled && (!portal.ready || !portal.risk_ack)
                      ? setSetup(portal)
                      : toggle.mutate(portal)
                  }
                />
                <span />
              </label>
            </div>
            <div className="portal-actions">
              <button
                className="button secondary small"
                disabled={!data.enabled || !data.local_only}
                onClick={() => setSetup({ ...portal, access_mode: "session" })}
              >
                <LogIn size={14} />
                {portal.session.authenticated ? "Reconnect" : "Sign in"}
              </button>
              {portal.public_supported && (
                <button
                  className="button text small"
                  disabled={!data.enabled || !data.local_only}
                  onClick={() => setSetup({ ...portal, access_mode: "public" })}
                >
                  Try without sign-in
                </button>
              )}
              <button
                className="button text small"
                onClick={() => setImporting(portal)}
              >
                <FilePlus2 size={14} />
                Import job
              </button>
              <a
                className="button text small"
                href={safeLink(portal.search_url)}
                target="_blank"
                rel="noreferrer noopener"
              >
                Open jobs
                <ArrowUpRight size={14} />
              </a>
              <IconButton
                label={`Configure ${portal.name} portal`}
                onClick={() => setSetup(portal)}
              >
                <Settings2 size={16} />
              </IconButton>
              {portal.session.authenticated && (
                <IconButton
                  label={`Disconnect ${portal.name}`}
                  onClick={() => setDisconnect(portal)}
                >
                  <LogOut size={16} />
                </IconButton>
              )}
              {portal.ready && (
                <button
                  className="button text small"
                  disabled={task.isPending}
                  onClick={() => task.mutate(`/sources/${portal.key}/test`)}
                >
                  Check access
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      {enableOpen && (
        <Confirm
          title="Enable optional portal access?"
          detail={data.risk_notice}
          action="Enable portal access"
          onClose={() => setEnableOpen(false)}
          onConfirm={async () => {
            await changeAccess.mutateAsync(true);
          }}
        />
      )}
      {setup && (
        <PortalSetup
          portal={setup}
          access={data}
          onClose={() => setSetup(null)}
          onTask={(id) => setTaskId(id)}
        />
      )}
      {importing && (
        <PortalImport portal={importing} onClose={() => setImporting(null)} />
      )}
      {disconnect && (
        <Confirm
          title={`Disconnect ${disconnect.name}?`}
          detail="The local browser session and cookies will be removed, and this portal will be excluded from searches. Imported and saved jobs will remain."
          action="Disconnect"
          onClose={() => setDisconnect(null)}
          onConfirm={async () => {
            await request(`/portals/${disconnect.key}/session`, {
              method: "DELETE",
            });
            await refreshPortals();
          }}
        />
      )}
      {!visible.length && <EmptyState title="No portals match this search" />}
    </section>
  );
}

function PortalTask({ id }: { id: string }) {
  const result = useQuery({
    queryKey: ["portal-task", id],
    queryFn: ({ signal }) =>
      request<{
        task: Task;
        result: {
          session_saved?: boolean;
          detail?: string;
          selectors?: { card?: { matched?: number } };
        };
        error: string;
      }>(`/tasks/${id}`, { signal }),
    refetchInterval: (query) =>
      !query.state.data ||
      ["queued", "running"].includes(query.state.data.task.status)
        ? 1000
        : false,
  });
  const cancel = useMutation({
    mutationFn: () => post(`/tasks/${id}/cancel`),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["portal-task", id] }),
  });
  const status = result.data?.task.status;
  useEffect(() => {
    if (status && ["done", "failed", "cancelled"].includes(status)) {
      void refreshPortals();
    }
  }, [id, status]);
  if (result.isError) return <ErrorState error={result.error} />;
  if (!result.data) return <Spinner />;
  const { task, error, result: payload } = result.data;
  const active = ["queued", "running"].includes(task.status);
  return (
    <div
      className={`portal-task fact-notice ${task.status === "failed" ? "warning" : "success"}`}
      role="status"
    >
      {active ? (
        <Spinner />
      ) : task.status === "failed" ? (
        <AlertCircle size={18} />
      ) : (
        <ShieldCheck size={18} />
      )}
      <div>
        <strong>{task.label}</strong>
        <p>
          {task.status === "failed"
            ? error || task.error
            : task.status === "cancelled"
              ? "Cancelled"
              : active
                ? task.kind === "sign-in"
                  ? "Complete sign-in and any verification in the portal browser. Passwords are not entered in JobLookup."
                  : task.message || "Queued"
                : payload.detail ||
                  (payload.selectors
                    ? `${payload.selectors.card?.matched ?? 0} job cards readable.`
                    : "Completed")}
        </p>
      </div>
      {active && (
        <button
          className="button secondary small"
          disabled={cancel.isPending}
          onClick={() => cancel.mutate()}
        >
          Cancel
        </button>
      )}
    </div>
  );
}

function PortalSetup({
  portal,
  access,
  onClose,
  onTask,
}: {
  portal: Portal;
  access: Portals;
  onClose: () => void;
  onTask: (id: string) => void;
}) {
  const [mode, setMode] = useState(portal.access_mode);
  const [acknowledged, setAcknowledged] = useState(portal.risk_ack);
  const [terms, setTerms] = useState(
    Array.isArray(portal.config.extra_terms)
      ? portal.config.extra_terms.join(", ")
      : "",
  );
  const notify = useToast();
  const save = useMutation({
    mutationFn: async (signin: boolean) => {
      await request(`/portals/${portal.key}`, {
        method: "PUT",
        body: JSON.stringify({
          enabled: true,
          acknowledged,
          access_mode: mode,
          extra_terms: terms
            .split(/[,\n]/)
            .map((term) => term.trim())
            .filter(Boolean),
        }),
      });
      await refreshPortals();
      if (signin) {
        const payload = await post<{ task: Task }>(
          `/sources/${portal.key}/signin`,
        );
        onTask(payload.task.id);
        await refreshWorkspace();
      }
    },
    onSuccess: (_, signin) => {
      notify(
        signin ? `Opening ${portal.name} sign-in.` : `${portal.name} enabled.`,
      );
      onClose();
    },
  });
  const blocked =
    !access.enabled || !access.local_only || !acknowledged || save.isPending;
  return (
    <Dialog title={`${portal.name} access`} onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate(mode === "session");
        }}
      >
        <div className="dialog-body">
          <Field id="portal-access-mode" label="Access mode">
            <select
              id="portal-access-mode"
              value={mode}
              onChange={(event) =>
                setMode(event.target.value as "session" | "public")
              }
            >
              <option value="session">Sign in with my account</option>
              {portal.public_supported && (
                <option value="public">Public listings (no sign-in)</option>
              )}
            </select>
          </Field>
          <p className="portal-access-description">
            {mode === "session"
              ? "A separate local browser opens on the portal's own sign-in page. Complete sign-in there; it closes after your session is verified. Session cookies remain on this device until you disconnect."
              : "Only the ordinary public search page is requested, without saved login cookies. Some portals block public access or publish incomplete descriptions. Access stops at sign-in or verification walls."}
          </p>
          <Field id="portal-terms" label="Extra target roles" optional>
            <input
              id="portal-terms"
              value={terms}
              onChange={(event) => setTerms(event.target.value)}
              placeholder="Additional role titles"
            />
          </Field>
          <div className="portal-risk">
            <AlertCircle size={18} />
            <p>{access.risk_notice}</p>
          </div>
          <label className="portal-consent">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
            I understand the restrictions and have permission to use automated
            access.
          </label>
          {!access.enabled && (
            <p className="model-picker-status">
              Enable portal access before connecting a portal.
            </p>
          )}
          {mode === "session" && !access.browser.browser_ready && (
            <p className="model-picker-status">
              Install browser support in Job sources before signing in.
            </p>
          )}
          {save.isError && <ErrorState error={save.error} />}
        </div>
        <footer className="dialog-footer">
          <button className="button secondary" type="button" onClick={onClose}>
            Cancel
          </button>
          {mode === "session" && portal.session.authenticated && (
            <button
              className="button secondary"
              type="button"
              disabled={blocked}
              onClick={() => save.mutate(false)}
            >
              Use saved session
            </button>
          )}
          <button
            className="button primary"
            disabled={
              blocked || (mode === "session" && !access.browser.browser_ready)
            }
          >
            {save.isPending ? (
              <Spinner />
            ) : mode === "session" ? (
              <LogIn size={15} />
            ) : (
              <Globe2 size={15} />
            )}
            {mode === "session" ? "Save & sign in" : "Enable public access"}
          </button>
        </footer>
      </form>
    </Dialog>
  );
}

function PortalImport({
  portal,
  onClose,
}: {
  portal: Portal;
  onClose: () => void;
}) {
  const [form, setForm] = useState({
    title: "",
    company: "",
    location: "",
    description: "",
    url: "",
    posted_at: "",
    work_mode: "unknown",
    employment: "unknown",
  });
  const [jobId, setJobId] = useState<number | null>(null);
  const update = (key: keyof typeof form, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));
  const save = useMutation({
    mutationFn: () =>
      post<{ job_id: number }>(`/portals/${portal.key}/import`, {
        ...form,
        posted_at: form.posted_at || null,
      }),
    onSuccess: async (result) => {
      setJobId(result.job_id);
      await refreshWorkspace();
    },
  });
  return (
    <Dialog title={`Import a ${portal.name} job`} onClose={onClose}>
      {jobId ? (
        <>
          <div className="dialog-body">
            <div className="fact-notice success">
              <ShieldCheck size={20} />
              <div>
                <strong>Job imported</strong>
                <p>
                  The posting is now available for matching and application
                  tracking.
                </p>
              </div>
            </div>
          </div>
          <footer className="dialog-footer">
            <button className="button secondary" onClick={onClose}>
              Close
            </button>
            <Link
              className="button primary"
              onClick={onClose}
              to={`/matches?view=all&job=${jobId}`}
            >
              View match
              <ArrowUpRight size={15} />
            </Link>
          </footer>
        </>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <div className="dialog-body">
            <p className="portal-access-description">
              Paste details from a posting you can access. No sign-in or
              automated page request is needed. Leave unknown fields empty.
            </p>
            <Field id="import-url" label="Original posting URL">
              <input
                id="import-url"
                type="url"
                required
                value={form.url}
                onChange={(event) => update("url", event.target.value)}
                placeholder={`${portal.homepage}/...`}
              />
            </Field>
            <Field id="import-title" label="Job title">
              <input
                id="import-title"
                required
                minLength={2}
                maxLength={300}
                value={form.title}
                onChange={(event) => update("title", event.target.value)}
              />
            </Field>
            <Field id="import-company" label="Company">
              <input
                id="import-company"
                required
                maxLength={200}
                value={form.company}
                onChange={(event) => update("company", event.target.value)}
              />
            </Field>
            <div className="form-grid">
              <Field id="import-location" label="Location" optional>
                <input
                  id="import-location"
                  value={form.location}
                  onChange={(event) => update("location", event.target.value)}
                />
              </Field>
              <Field id="import-date" label="Posting date" optional>
                <input
                  id="import-date"
                  type="date"
                  value={form.posted_at}
                  onChange={(event) => update("posted_at", event.target.value)}
                />
              </Field>
            </div>
            <div className="form-grid">
              <Field id="import-mode" label="Work arrangement">
                <select
                  id="import-mode"
                  value={form.work_mode}
                  onChange={(event) => update("work_mode", event.target.value)}
                >
                  <option value="unknown">Not stated</option>
                  <option value="remote">Remote</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="onsite">On site</option>
                </select>
              </Field>
              <Field id="import-employment" label="Employment">
                <select
                  id="import-employment"
                  value={form.employment}
                  onChange={(event) => update("employment", event.target.value)}
                >
                  <option value="unknown">Not stated</option>
                  <option value="full-time">Full-time</option>
                  <option value="part-time">Part-time</option>
                  <option value="contract">Contract</option>
                  <option value="internship">Internship</option>
                </select>
              </Field>
            </div>
            <Field id="import-description" label="Job description">
              <textarea
                id="import-description"
                required
                minLength={80}
                maxLength={100000}
                rows={7}
                value={form.description}
                onChange={(event) => update("description", event.target.value)}
              />
            </Field>
            {save.isError && <ErrorState error={save.error} />}
          </div>
          <footer className="dialog-footer">
            <button
              className="button secondary"
              type="button"
              onClick={onClose}
            >
              Cancel
            </button>
            <button className="button primary" disabled={save.isPending}>
              {save.isPending ? <Spinner /> : <FilePlus2 size={15} />}Import job
            </button>
          </footer>
        </form>
      )}
    </Dialog>
  );
}
