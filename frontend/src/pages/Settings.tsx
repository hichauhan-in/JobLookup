import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  Cpu,
  Eye,
  EyeOff,
  Globe2,
  History,
  KeyRound,
  LockKeyhole,
  Plug,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
} from "lucide-react";
import {
  errorMessage,
  post,
  queryClient,
  refreshWorkspace,
  request,
  useWorkspace,
} from "../api";
import { dateLabel, label, safeLink } from "../lib/format";
import type {
  BridgeModels,
  Connection,
  Run,
  Source,
  Sources,
  Task,
} from "../types";
import {
  Confirm,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  IconButton,
  PageHead,
  Spinner,
} from "../components/ui";
import { useToast } from "../components/notifications";
import { PortalSources } from "../components/PortalSources";

export default function Settings() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "connection";
  const tabs = [
    { id: "connection", name: "AI connection", icon: Plug },
    { id: "sources", name: "Job sources", icon: Globe2 },
    { id: "history", name: "Search history", icon: History },
    { id: "data", name: "Workspace", icon: ShieldCheck },
  ];
  return (
    <>
      <PageHead
        eyebrow="YOUR WORKSPACE, YOUR WAY"
        title="Settings"
        detail="Connections, sources, and search activity."
      />
      <nav className="tabs settings-tabs" aria-label="Settings sections">
        {tabs.map((item) => (
          <button
            key={item.id}
            className={tab === item.id ? "active" : ""}
            aria-current={tab === item.id ? "page" : undefined}
            onClick={() => setParams({ tab: item.id }, { replace: true })}
          >
            <item.icon size={16} />
            {item.name}
          </button>
        ))}
      </nav>
      <div className="settings-content">
        {tab === "sources" ? (
          <SourcesSettings />
        ) : tab === "history" ? (
          <HistorySettings />
        ) : tab === "data" ? (
          <DataSettings />
        ) : (
          <ConnectionSettings />
        )}
      </div>
    </>
  );
}

function ConnectionSettings() {
  const connection = useQuery({
    queryKey: ["connections"],
    queryFn: ({ signal }) => request<Connection>("/connections", { signal }),
  });
  if (connection.isPending)
    return (
      <div className="detail-loading">
        <Spinner />
      </div>
    );
  if (connection.isError)
    return (
      <ErrorState
        error={connection.error}
        retry={() => void connection.refetch()}
      />
    );
  return <ConnectionForm initial={connection.data} />;
}

function ConnectionForm({ initial }: { initial: Connection }) {
  const [kind, setKind] = useState(
    ["vscode", "copilot_cli"].includes(initial.provider)
      ? initial.provider
      : initial.preset || "custom",
  );
  const [model, setModel] = useState(initial.model);
  const [endpoint, setEndpoint] = useState(initial.base_url);
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [keySet, setKeySet] = useState(initial.key_set);
  const [testId, setTestId] = useState<string | null>(null);
  const notify = useToast();
  const preset = initial.presets.find((item) => item.key === kind);
  const isBridge = kind === "vscode";
  const isCli = kind === "copilot_cli";
  const useApi = !isBridge && !isCli;
  const bridgeModels = useQuery({
    queryKey: ["bridge-models"],
    queryFn: ({ signal }) =>
      request<BridgeModels>("/connections/vscode/models", { signal }),
    enabled: isBridge,
    staleTime: 0,
    retry: false,
  });
  const bridgeModelNames = bridgeModels.data?.models || [];
  const unavailableModel = !!model && !bridgeModelNames.includes(model);
  const bridgeModelBlocked =
    isBridge &&
    (bridgeModels.isFetching ||
      bridgeModels.isPending ||
      bridgeModels.isError ||
      !bridgeModelNames.length ||
      unavailableModel);
  const select = (value: string) => {
    setKind(value);
    setTestId(null);
    setApiKey("");
    setKeySet(false);
    const chosen = initial.presets.find((item) => item.key === value);
    setEndpoint(chosen?.base_url || "");
    setModel(chosen?.suggested_models[0] || "");
  };
  const save = useMutation({
    mutationFn: async (test: boolean) => {
      if (bridgeModelBlocked) {
        throw new Error(
          "Choose an available bridge model or refresh the model list.",
        );
      }
      const response = await request<Connection>("/connections", {
        method: "PUT",
        body: JSON.stringify({
          provider:
            isBridge || isCli ? kind : preset?.provider || "openai_compat",
          preset: kind,
          base_url: endpoint,
          model,
          ...(apiKey ? { api_key: apiKey } : {}),
        }),
      });
      setApiKey("");
      setKeySet(response.key_set);
      if (test) {
        const result = await post<{ task: Task }>("/connections/test");
        setTestId(result.task.id);
      }
      await queryClient.invalidateQueries({ queryKey: ["connections"] });
      await refreshWorkspace();
    },
    onSuccess: (_, test) =>
      notify(
        test ? "Connection saved. Testing your model." : "Connection saved.",
      ),
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const test = useQuery({
    queryKey: ["connection-test", testId],
    queryFn: ({ signal }) =>
      request<{
        task: Task;
        result: { ok?: boolean; detail?: string; model?: string };
        error: string;
      }>(`/tasks/${testId}`, { signal }),
    enabled: !!testId,
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.task.status || "")
        ? 1000
        : false,
  });
  const testing =
    testId &&
    (!test.data || ["queued", "running"].includes(test.data.task.status));
  return (
    <div className="connection-layout">
      <form
        className="connection-form"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate(true);
        }}
      >
        <div className="section-title">
          <h2>AI provider</h2>
          <span className="subtle-badge">Optional</span>
        </div>
        <Field id="provider" label="Connection">
          <select
            id="provider"
            value={kind}
            onChange={(event) => select(event.target.value)}
          >
            <optgroup label="GitHub Copilot">
              <option value="vscode">VS Code bridge</option>
              <option value="copilot_cli">Copilot CLI</option>
            </optgroup>
            <optgroup label="Local models & APIs">
              {initial.presets.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label}
                </option>
              ))}
            </optgroup>
          </select>
        </Field>
        {useApi && (
          <Field id="endpoint" label="API endpoint">
            <input
              id="endpoint"
              type="url"
              required
              value={endpoint}
              onChange={(event) => {
                setEndpoint(event.target.value);
                setTestId(null);
              }}
              placeholder="https://your-provider.example/v1"
              spellCheck={false}
            />
          </Field>
        )}
        <Field
          id="model-name"
          label={kind === "azure_openai" ? "Deployment name" : "Model"}
          optional={isCli}
        >
          {isBridge ? (
            <>
              <div className="model-picker">
                <select
                  id="model-name"
                  value={model}
                  disabled={
                    bridgeModels.isFetching ||
                    !bridgeModelNames.length ||
                    save.isPending ||
                    !!testing
                  }
                  onChange={(event) => {
                    setModel(event.target.value);
                    setTestId(null);
                  }}
                >
                  <option value="">
                    {bridgeModels.isPending
                      ? "Loading models..."
                      : !bridgeModelNames.length
                        ? "No models available"
                        : bridgeModels.data?.default_model
                          ? `Automatic (${bridgeModels.data.default_model})`
                          : "Automatic (bridge default)"}
                  </option>
                  {unavailableModel && (
                    <option value={model} disabled>
                      {model} (
                      {bridgeModels.isSuccess ? "unavailable" : "saved"})
                    </option>
                  )}
                  {bridgeModelNames.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
                <IconButton
                  label="Refresh bridge models"
                  disabled={
                    bridgeModels.isFetching || save.isPending || !!testing
                  }
                  onClick={() => void bridgeModels.refetch()}
                >
                  {bridgeModels.isFetching ? (
                    <Spinner label="Loading bridge models" />
                  ) : (
                    <RefreshCw size={17} />
                  )}
                </IconButton>
              </div>
              {bridgeModels.isError && (
                <ErrorState
                  error={bridgeModels.error}
                  retry={() => void bridgeModels.refetch()}
                />
              )}
              {bridgeModels.isSuccess &&
                (!bridgeModelNames.length || !bridgeModels.data.available) && (
                  <p className="model-picker-status" role="status">
                    {bridgeModels.data.detail ||
                      "The bridge reported no available models."}
                  </p>
                )}
              {bridgeModels.isSuccess &&
                bridgeModelNames.length > 0 &&
                unavailableModel && (
                  <p className="model-picker-status error" role="alert">
                    The selected model is no longer available from this bridge.
                  </p>
                )}
            </>
          ) : (
            <>
              <input
                id="model-name"
                list="model-suggestions"
                required={useApi}
                value={model}
                onChange={(event) => {
                  setModel(event.target.value);
                  setTestId(null);
                }}
                placeholder={
                  isCli ? "Default available model" : "Model identifier"
                }
                spellCheck={false}
              />
              <datalist id="model-suggestions">
                {preset?.suggested_models.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
            </>
          )}
        </Field>
        {useApi && (
          <Field id="api-key" label="API key" optional>
            <div className="password-input">
              <input
                id="api-key"
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                autoComplete="new-password"
                placeholder={
                  keySet
                    ? "Saved securely. Leave blank to keep it."
                    : "Not configured"
                }
              />
              <IconButton
                label={showKey ? "Hide API key" : "Show API key"}
                onClick={() => setShowKey(!showKey)}
              >
                {showKey ? <EyeOff size={17} /> : <Eye size={17} />}
              </IconButton>
            </div>
            {keySet && (
              <span className="field-status">
                <LockKeyhole size={12} />
                Key saved for this endpoint
              </span>
            )}
          </Field>
        )}
        <div className="connection-actions">
          <button
            type="button"
            className="button secondary"
            disabled={save.isPending || !!testing || bridgeModelBlocked}
            onClick={() => save.mutate(false)}
          >
            Save connection
          </button>
          <button
            className="button primary"
            disabled={save.isPending || !!testing || bridgeModelBlocked}
          >
            {save.isPending || testing ? <Spinner /> : <Plug size={16} />}Save &
            test
          </button>
        </div>
        {save.isError && <ErrorState error={save.error} />}
        {test.data?.task.status === "done" && (
          <div className="fact-notice success" role="status">
            <CheckCircle2 size={19} />
            <div>
              <strong>Connection verified</strong>
              <p>
                {test.data.result.model || "Your model"} returned a response.
              </p>
            </div>
          </div>
        )}
        {test.data?.task.status === "failed" && (
          <div className="fact-notice warning" role="alert">
            <AlertCircle size={19} />
            <div>
              <strong>Connection could not be verified</strong>
              <p>{test.data.error || test.data.task.error}</p>
            </div>
          </div>
        )}
      </form>
      <aside className="connection-aside">
        <div className="engine-status">
          <div className="engine-icon">
            <Cpu size={26} strokeWidth={1.5} />
          </div>
          <h3>Matching engine</h3>
          <p className="status-line">
            <span className="status-dot" />
            Local evidence engine active
          </p>
          <dl>
            <div>
              <dt>Profile processing</dt>
              <dd>On this device</dd>
            </div>
            <div>
              <dt>Job ranking</dt>
              <dd>On this device</dd>
            </div>
            <div>
              <dt>AI requests</dt>
              <dd>On demand only</dd>
            </div>
            <div>
              <dt>Automatic provider fallback</dt>
              <dd>Off</dd>
            </div>
          </dl>
        </div>
        {(isBridge || isCli) && (
          <div className="connection-requirements">
            <h3>{isBridge ? "VS Code bridge" : "Copilot CLI"}</h3>
            <dl>
              <div>
                <dt>Account</dt>
                <dd>GitHub Copilot</dd>
              </div>
              <div>
                <dt>Transport</dt>
                <dd>{isBridge ? "Authenticated localhost" : "Local CLI"}</dd>
              </div>
            </dl>
            <code>
              {isBridge
                ? "JobLookup Bridge: Restart Server"
                : "copilot --version"}
            </code>
          </div>
        )}
      </aside>
    </div>
  );
}

function SourcesSettings() {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const [editing, setEditing] = useState<Source | null>(null);
  const [region, setRegion] = useState("");
  const notify = useToast();
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: ({ signal }) => request<Sources>("/sources", { signal }),
  });
  const reload = async () => {
    await queryClient.invalidateQueries({ queryKey: ["sources"] });
    await refreshWorkspace();
  };
  const toggle = useMutation({
    mutationFn: (source: Source) =>
      post(`/sources/${source.key}/enabled`, { enabled: !source.enabled }),
    onSuccess: reload,
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const recommend = useMutation({
    mutationFn: () =>
      post("/sources/region", {
        code: region || sources.data?.region.code || "in",
        apply: true,
        companies: 12,
        replace: false,
      }),
    onSuccess: async () => {
      notify("Recommended public sources configured.");
      await reload();
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  if (sources.isPending)
    return (
      <div className="detail-loading">
        <Spinner />
      </div>
    );
  if (sources.isError)
    return (
      <ErrorState error={sources.error} retry={() => void sources.refetch()} />
    );
  const publicSources = sources.data.sources.filter(
    (source) => source.tier !== "b",
  );
  const displayed = publicSources.filter(
    (source) =>
      kind !== "portals" &&
      source.name.toLowerCase().includes(query.toLowerCase()) &&
      (kind === "all" ||
        (kind === "boards"
          ? source.tier === "ats"
          : kind === "keyed"
            ? source.requires_key
            : source.tier === "a" && !source.requires_key)),
  );
  return (
    <>
      <div className="section-title">
        <div>
          <h2>Job sources</h2>
          <p className="muted small">
            {
              sources.data.sources.filter(
                (source) => source.enabled && source.ready,
              ).length
            }{" "}
            active and ready
          </p>
        </div>
        <div className="button-row">
          <select
            aria-label="Source region"
            value={region || sources.data.region.code}
            onChange={(event) => setRegion(event.target.value)}
          >
            {sources.data.regions.map((item) => (
              <option value={item.code} key={item.code}>
                {item.name}
              </option>
            ))}
          </select>
          <button
            className="button primary"
            disabled={recommend.isPending}
            onClick={() => recommend.mutate()}
          >
            {recommend.isPending ? <Spinner /> : <Sparkles size={15} />}Use
            recommended
          </button>
        </div>
      </div>
      <div className="results-toolbar">
        <div className="search-input">
          <Search size={16} />
          <input
            aria-label="Search sources"
            placeholder="Search job sources"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <select
          aria-label="Source type"
          value={kind}
          onChange={(event) => setKind(event.target.value)}
        >
          <option value="all">All sources</option>
          <option value="feeds">Public feeds</option>
          <option value="boards">Employer boards</option>
          <option value="keyed">Keyed APIs</option>
          <option value="portals">Job portals</option>
        </select>
      </div>
      <div className="source-list">
        {displayed.map((source) => (
          <div className="source-row" key={source.key}>
            <div
              className={`source-icon ${source.tier === "ats" ? "blue" : "green"}`}
            >
              {source.requires_key ? (
                <KeyRound size={18} />
              ) : (
                <Globe2 size={18} />
              )}
            </div>
            <div className="source-main">
              <strong>{source.name}</strong>
              <p>
                {source.tier === "ats"
                  ? "Employer board"
                  : source.requires_key
                    ? "Keyed API"
                    : "Public feed"}
                {source.last_count > 0
                  ? ` · ${source.last_count} postings last search`
                  : ""}
              </p>
              {source.last_error && source.last_status === "failed" && (
                <p className="source-error" title={source.last_error}>
                  Last search failed
                </p>
              )}
            </div>
            <span className={`readiness ${source.ready ? "ready" : ""}`}>
              {source.ready ? "Ready" : "Setup needed"}
            </span>
            <IconButton
              label={`Configure ${source.name}`}
              onClick={() => setEditing(source)}
            >
              <Settings2 size={17} />
            </IconButton>
            <label className="switch-control">
              <input
                type="checkbox"
                role="switch"
                aria-label={`Enable ${source.name}`}
                checked={source.enabled}
                disabled={toggle.isPending}
                onChange={() => {
                  if (!source.enabled && !source.ready) setEditing(source);
                  else toggle.mutate(source);
                }}
              />
              <span />
            </label>
          </div>
        ))}
      </div>
      {(kind === "all" || kind === "portals") && (
        <PortalSources query={query} />
      )}
      {!displayed.length && kind !== "all" && kind !== "portals" && (
        <EmptyState title="No sources found" />
      )}
      {editing && (
        <SourceConfiguration
          source={editing}
          onClose={() => setEditing(null)}
          onSaved={reload}
        />
      )}
    </>
  );
}

const SECRET_FIELDS: Record<string, [string, string][]> = {
  adzuna: [
    ["adzuna_app_id", "Application ID"],
    ["adzuna_app_key", "Application key"],
  ],
  jooble: [["jooble", "API key"]],
  usajobs: [
    ["usajobs_email", "Registered email"],
    ["usajobs", "Authorization key"],
  ],
  findwork: [["findwork", "API key"]],
  reed: [["reed", "API key"]],
};

function SourceConfiguration({
  source,
  onClose,
  onSaved,
}: {
  source: Source;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(source.config);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const notify = useToast();
  const secrets = useQuery({
    queryKey: ["source-secrets"],
    queryFn: ({ signal }) =>
      request<{ set: Record<string, boolean> }>("/secrets", { signal }),
  });
  const save = useMutation({
    mutationFn: async () => {
      for (const [name, value] of Object.entries(keys))
        if (value.trim()) await post("/secrets", { name, value });
      await post(`/sources/${source.key}/config`, { config: values });
      await post(`/sources/${source.key}/enabled`, { enabled: true });
    },
    onSuccess: async () => {
      await onSaved();
      notify(`${source.name} saved.`);
      onClose();
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const fields = source.fields.filter((field) => field.kind !== "password");
  return (
    <Dialog title={source.name} onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <div className="dialog-body">
          <div className="source-dialog-meta">
            <span className="subtle-badge">
              {source.tier === "ats" ? "Employer board" : "Public API"}
            </span>
            {safeLink(source.homepage) && (
              <a
                href={source.homepage}
                target="_blank"
                rel="noreferrer noopener"
              >
                Website
                <ArrowUpRight size={14} />
              </a>
            )}
          </div>
          {source.last_error && (
            <div className="fact-notice warning">
              <AlertCircle size={16} />
              <p>{source.last_error}</p>
            </div>
          )}
          {(SECRET_FIELDS[source.key] || []).map(([key, name]) => (
            <Field key={key} id={`secret-${key}`} label={name}>
              <input
                id={`secret-${key}`}
                type={key.includes("email") ? "email" : "password"}
                value={keys[key] || ""}
                required={!secrets.data?.set[key]}
                autoComplete="new-password"
                onChange={(event) =>
                  setKeys((current) => ({
                    ...current,
                    [key]: event.target.value,
                  }))
                }
                placeholder={
                  secrets.data?.set[key]
                    ? "Saved. Leave blank to keep."
                    : "Not set"
                }
              />
            </Field>
          ))}
          {fields.map((field) => (
            <Field
              key={field.key}
              id={`config-${field.key}`}
              label={field.label}
            >
              {field.kind === "boolean" ? (
                <input
                  id={`config-${field.key}`}
                  type="checkbox"
                  checked={!!values[field.key]}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      [field.key]: event.target.checked,
                    }))
                  }
                />
              ) : field.kind === "list" ? (
                <textarea
                  id={`config-${field.key}`}
                  rows={5}
                  required={field.required}
                  value={
                    Array.isArray(values[field.key])
                      ? (values[field.key] as string[]).join("\n")
                      : String(values[field.key] || "")
                  }
                  placeholder={field.placeholder}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      [field.key]: event.target.value
                        .split(/[,\n]/)
                        .map((item) => item.trim())
                        .filter(Boolean),
                    }))
                  }
                />
              ) : (
                <input
                  id={`config-${field.key}`}
                  type={field.kind === "number" ? "number" : "text"}
                  min={field.kind === "number" ? 1 : undefined}
                  required={field.required}
                  placeholder={field.placeholder}
                  value={String(values[field.key] ?? "")}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      [field.key]:
                        field.kind === "number"
                          ? Number(event.target.value)
                          : event.target.value,
                    }))
                  }
                />
              )}
            </Field>
          ))}
          {source.guide.examples?.length ? (
            <details className="source-examples">
              <summary>
                Example addresses
                <ChevronDown size={14} />
              </summary>
              {source.guide.examples.slice(0, 3).map((example) => (
                <code key={example.enter}>{example.enter}</code>
              ))}
            </details>
          ) : null}
          <div className="source-links">
            {source.guide.links
              ?.filter((link) => safeLink(link.url))
              .map((link) => (
                <a
                  key={link.url}
                  href={link.url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {link.label}
                  <ArrowUpRight size={14} />
                </a>
              ))}
          </div>
          {save.isError && <ErrorState error={save.error} />}
        </div>
        <footer className="dialog-footer">
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary" disabled={save.isPending}>
            {save.isPending && <Spinner />}Save & enable
          </button>
        </footer>
      </form>
    </Dialog>
  );
}

function HistorySettings() {
  const [clearing, setClearing] = useState(false);
  const [removing, setRemoving] = useState<number | null>(null);
  const notify = useToast();
  const history = useQuery({
    queryKey: ["history"],
    queryFn: ({ signal }) => request<{ runs: Run[] }>("/history", { signal }),
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["history"] });
    await refreshWorkspace();
  };
  return (
    <>
      <div className="section-title">
        <h2>Search history</h2>
        <button
          className="button secondary small"
          disabled={!history.data?.runs.length}
          onClick={() => setClearing(true)}
        >
          <Trash2 size={15} />
          Clear history
        </button>
      </div>
      {history.isPending ? (
        <Spinner />
      ) : history.isError ? (
        <ErrorState error={history.error} />
      ) : !history.data.runs.length ? (
        <EmptyState title="No searches yet">
          <Link className="button primary" to="/matches">
            Back to matches
            <ArrowRight size={15} />
          </Link>
        </EmptyState>
      ) : (
        <div className="history-list">
          {history.data.runs.map((run) => (
            <article key={run.id} className="history-entry">
              <div className="history-summary">
                <div className={`run-status ${run.status}`}>
                  <History size={17} />
                </div>
                <div>
                  <strong>{dateLabel(run.started_at)}</strong>
                  <p>{run.sources.length} sources</p>
                </div>
                <span className={`subtle-badge ${run.status}`}>
                  {run.status === "ok" ? "Completed" : label(run.status)}
                </span>
                <div className="run-count">
                  <strong>{run.result_count}</strong>
                  <span>postings</span>
                </div>
                <div className="run-count">
                  <strong>{run.new_count}</strong>
                  <span>new</span>
                </div>
                <IconButton
                  label={`Delete search ${run.id}`}
                  disabled={run.status === "running"}
                  onClick={() => setRemoving(run.id)}
                >
                  <Trash2 size={16} />
                </IconButton>
              </div>
              <details className="run-report">
                <summary>
                  Source report
                  <ChevronDown size={14} />
                </summary>
                <div className="run-source-grid">
                  {run.sources.map((key) => (
                    <div key={key}>
                      <span>{label(key)}</span>
                      <span>
                        {run.stats.failures?.[key]
                          ? "Failed"
                          : `${run.stats.by_source?.[key] ?? 0} postings`}
                      </span>
                      {run.stats.failures?.[key] && (
                        <p className="error-text">{run.stats.failures[key]}</p>
                      )}
                    </div>
                  ))}
                </div>
              </details>
            </article>
          ))}
        </div>
      )}
      {clearing && (
        <Confirm
          title="Clear search history?"
          detail="Completed search records will be removed. Stored jobs and applications will not be deleted."
          action="Clear history"
          onClose={() => setClearing(false)}
          onConfirm={async () => {
            await request("/history", { method: "DELETE" });
            await refresh();
            notify("Search history cleared.");
          }}
        />
      )}
      {removing != null && (
        <Confirm
          title="Delete this search record?"
          detail="The record will be removed. Its job postings will remain available."
          action="Delete record"
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            await request(`/history/${removing}`, { method: "DELETE" });
            await refresh();
            notify("Search record deleted.");
          }}
        />
      )}
    </>
  );
}

function DataSettings() {
  const workspace = useWorkspace();
  return (
    <section className="data-settings">
      <div className="section-title">
        <h2>Local workspace</h2>
        <ShieldCheck size={22} />
      </div>
      <dl className="property-list">
        <div>
          <dt>Resume files</dt>
          <dd>{workspace.data?.counts.cvs ?? 0} stored locally</dd>
        </div>
        <div>
          <dt>Job postings</dt>
          <dd>{workspace.data?.counts.jobs ?? 0} stored locally</dd>
        </div>
        <div>
          <dt>Applications</dt>
          <dd>{workspace.data?.counts.tracked ?? 0} tracked</dd>
        </div>
        <div>
          <dt>Matching engine</dt>
          <dd>{workspace.data?.matching.engine || "Local evidence"}</dd>
        </div>
        <div>
          <dt>Portal access</dt>
          <dd>Optional, with per-portal consent</dd>
        </div>
        <div>
          <dt>AI fallback to other providers</dt>
          <dd>Off</dd>
        </div>
      </dl>
      <div className="button-row">
        <Link className="button secondary" to="/matches">
          <SlidersHorizontal size={16} />
          Manage matches
        </Link>
        <Link className="button secondary" to="/applications">
          Manage applications
          <ArrowRight size={16} />
        </Link>
      </div>
    </section>
  );
}
