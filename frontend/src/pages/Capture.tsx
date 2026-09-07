import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ClipboardPaste,
  FileUp,
  Globe2,
  Import,
} from "lucide-react";
import { errorMessage, post, refreshWorkspace } from "../api";
import { ErrorState, Field, PageHead, Spinner } from "../components/ui";
import { useToast } from "../components/notifications";

type Draft = {
  url: string;
  title: string;
  company: string;
  location: string;
  description: string;
  work_mode?: string;
  employment?: string;
  posted_at?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string;
  salary_period?: string;
};

export default function Capture() {
  const [params, setParams] = useSearchParams();
  const [packet] = useState(params.get("packet") || "");
  useEffect(() => {
    if (params.has("packet")) setParams({}, { replace: true });
  }, [params, setParams]);
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [selected, setSelected] = useState(0);
  const notify = useToast();
  const fromBrowser = useQuery({
    queryKey: ["capture", packet],
    queryFn: () =>
      post<{ items: Draft[] }>("/capture/preview", { text: packet }),
    enabled: !!packet,
    retry: false,
    staleTime: Infinity,
  });
  const preview = useMutation({
    mutationFn: (fetchUrl: boolean) =>
      post<{ items: Draft[] }>("/capture/preview", {
        text,
        url,
        fetch_url: fetchUrl,
      }),
    onSuccess: () => {
      setSelected(0);
      setParams({}, { replace: true });
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const items = preview.data?.items || fromBrowser.data?.items || [];
  const draft = items[selected];
  return (
    <>
      <PageHead
        eyebrow="FROM ANYWHERE"
        title="Import job"
        detail="Public posting, browser capture, or a pasted job alert."
      >
        <Link to="/matches" className="button secondary">
          <ArrowLeft size={16} />
          Matches
        </Link>
      </PageHead>
      <div className="capture-layout">
        <section className="workflow-form">
          <Field id="capture-url" label="Original posting URL" optional>
            <input
              id="capture-url"
              type="url"
              value={url}
              placeholder="https://"
              onChange={(event) => setUrl(event.target.value)}
            />
          </Field>
          <button
            className="button secondary align-start"
            disabled={preview.isPending || !url.trim()}
            onClick={() => preview.mutate(true)}
          >
            {preview.isPending ? <Spinner /> : <Globe2 size={16} />}Read public
            page
          </button>
          <Field
            id="capture-text"
            label="Job description, alert email, or browser capture"
          >
            <textarea
              id="capture-text"
              rows={9}
              maxLength={250000}
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </Field>
          <div className="button-row">
            <button
              className="button primary"
              disabled={preview.isPending || !text.trim()}
              onClick={() => preview.mutate(false)}
            >
              <ClipboardPaste size={16} />
              Preview pasted content
            </button>
            <label className="button secondary file-button">
              <FileUp size={16} />
              Open file
              <input
                className="sr-only"
                type="file"
                accept=".txt,.eml,.html,.json"
                aria-label="Open job alert file"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  if (file.size > 250000) {
                    notify(
                      "Choose a text or email file smaller than 250 KB.",
                      "error",
                    );
                    return;
                  }
                  setText(await file.text());
                  event.target.value = "";
                }}
              />
            </label>
          </div>
          {preview.isError && <ErrorState error={preview.error} />}
          {packet && fromBrowser.isPending && (
            <Spinner label="Reading browser capture" />
          )}
          {fromBrowser.isError && <ErrorState error={fromBrowser.error} />}
          {items.length > 1 && (
            <section>
              <h2>Captured links ({items.length})</h2>
              <ul className="capture-candidates">
                {items.map((item, index) => (
                  <li key={`${item.url}-${index}`}>
                    <button
                      className={selected === index ? "selected" : ""}
                      onClick={() => setSelected(index)}
                    >
                      {item.title || "Job link"}
                      <small>{item.url}</small>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <p className="muted">
            Sign-in and verification walls are not bypassed. Captured content
            stays in this local workspace.
          </p>
        </section>
        <section className="workflow-form">
          <h2>Review posting</h2>
          {draft ? (
            <CaptureEditor key={JSON.stringify(draft)} initial={draft} />
          ) : (
            <p className="muted">No posting preview yet.</p>
          )}
        </section>
      </div>
    </>
  );
}

function CaptureEditor({ initial }: { initial: Draft }) {
  const [form, setForm] = useState(initial);
  const navigate = useNavigate();
  const notify = useToast();
  const save = useMutation({
    mutationFn: () =>
      post<{ job_id: number; created: boolean }>("/capture/import", {
        ...form,
        work_mode: form.work_mode || "unknown",
        employment: form.employment || "unknown",
        posted_at: form.posted_at || null,
      }),
    onSuccess: async (result) => {
      await refreshWorkspace();
      navigate(`/matches?view=all&job=${result.job_id}`, { replace: true });
      notify(
        result.created ? "Posting imported." : "Existing posting updated.",
      );
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  return (
    <form
      className="workflow-form"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate();
      }}
    >
      <Field id="import-title" label="Job title">
        <input
          id="import-title"
          required
          minLength={2}
          maxLength={300}
          value={form.title}
          onChange={(event) => setForm({ ...form, title: event.target.value })}
        />
      </Field>
      <Field id="import-company" label="Company">
        <input
          id="import-company"
          required
          maxLength={200}
          value={form.company}
          onChange={(event) =>
            setForm({ ...form, company: event.target.value })
          }
        />
      </Field>
      <Field id="import-url" label="Posting URL">
        <input
          id="import-url"
          required
          type="url"
          value={form.url}
          onChange={(event) => setForm({ ...form, url: event.target.value })}
        />
      </Field>
      <Field id="import-location" label="Location" optional>
        <input
          id="import-location"
          value={form.location}
          onChange={(event) =>
            setForm({ ...form, location: event.target.value })
          }
        />
      </Field>
      <div className="form-grid">
        <Field id="import-mode" label="Work arrangement">
          <select
            id="import-mode"
            value={form.work_mode || "unknown"}
            onChange={(event) =>
              setForm({ ...form, work_mode: event.target.value })
            }
          >
            <option value="unknown">Not stated</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On site</option>
          </select>
        </Field>
        <Field id="import-date" label="Posted date" optional>
          <input
            id="import-date"
            type="date"
            value={form.posted_at?.slice(0, 10) || ""}
            onChange={(event) =>
              setForm({ ...form, posted_at: event.target.value || null })
            }
          />
        </Field>
      </div>
      <Field id="import-description" label="Description">
        <textarea
          id="import-description"
          required
          minLength={80}
          maxLength={100000}
          rows={9}
          value={form.description}
          onChange={(event) =>
            setForm({ ...form, description: event.target.value })
          }
        />
      </Field>
      {save.isError && <ErrorState error={save.error} />}
      <button className="button primary align-start" disabled={save.isPending}>
        {save.isPending ? <Spinner /> : <Import size={16} />}Confirm import
      </button>
    </form>
  );
}
