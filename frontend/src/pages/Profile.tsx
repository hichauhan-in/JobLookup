import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useBlocker } from "react-router-dom";
import {
  Check,
  FileText,
  Link2,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  UserRound,
} from "lucide-react";
import {
  errorMessage,
  post,
  refreshWorkspace,
  request,
  useWorkspace,
} from "../api";
import type { Profile as ProfileData, Resume } from "../types";
import {
  Confirm,
  ErrorState,
  Field,
  IconButton,
  PageHead,
  Spinner,
  TagInput,
} from "../components/ui";
import { useToast } from "../components/notifications";
import { PreferenceFields } from "../components/PreferenceFields";

export default function Profile() {
  const workspace = useWorkspace();
  if (workspace.isPending)
    return (
      <div className="detail-loading">
        <Spinner />
      </div>
    );
  if (workspace.isError)
    return (
      <ErrorState
        error={workspace.error}
        retry={() => void workspace.refetch()}
      />
    );
  return (
    <ProfileEditor
      profile={workspace.data.profile.data}
      documents={workspace.data.cvs}
    />
  );
}

function ProfileEditor({
  profile,
  documents,
}: {
  profile: ProfileData;
  documents: Resume[];
}) {
  const [edits, setEdits] = useState<Partial<ProfileData>>({});
  const form = { ...profile, ...edits };
  const [remove, setRemove] = useState<Resume | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const notify = useToast();
  const dirty = Object.entries(edits).some(
    ([key, value]) =>
      JSON.stringify(value) !==
      JSON.stringify(profile[key as keyof ProfileData]),
  );
  const blocker = useBlocker(dirty);
  const set = <Key extends keyof ProfileData>(
    key: Key,
    value: ProfileData[Key],
  ) => setEdits((current) => ({ ...current, [key]: value }));
  useEffect(() => {
    if (!dirty) return;
    const prevent = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [dirty]);
  const save = useMutation({
    mutationFn: () => {
      const changes = Object.fromEntries(
        Object.entries(edits).filter(
          ([key, value]) =>
            JSON.stringify(value) !==
            JSON.stringify(profile[key as keyof ProfileData]),
        ),
      );
      return request<{ profile: { data: ProfileData } }>("/profile", {
        method: "PUT",
        body: JSON.stringify(changes),
      });
    },
    onSuccess: async () => {
      notify("Profile saved. Matches now use your updated preferences.");
      await refreshWorkspace();
      setEdits({});
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) {
        const body = new FormData();
        body.append("file", file);
        await request("/cvs", { method: "POST", body });
      }
    },
    onSuccess: async () => {
      notify("Document uploaded. Local extraction is running.");
      await refreshWorkspace();
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const primary = useMutation({
    mutationFn: (id: number) => post(`/cvs/${id}/primary`),
    onSuccess: () => refreshWorkspace(),
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const analyze = useMutation({
    mutationFn: (id: number) => post(`/cvs/${id}/analyze`),
    onSuccess: async () => {
      notify("AI resume analysis started.");
      await refreshWorkspace();
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const completed = [
    !!form.full_name,
    !!form.target_titles?.length,
    !!form.skills?.length,
    !!form.locations?.length,
  ].filter(Boolean).length;
  const toggle = (key: "work_modes" | "employment_types", value: string) =>
    set(
      key,
      form[key]?.includes(value)
        ? form[key]?.filter((item) => item !== value)
        : [...(form[key] || []), value],
    );
  return (
    <>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <PageHead
          eyebrow="THE STARTING POINT"
          title="Your profile"
          detail="Your experience. Your preferences. Your next step."
        >
          {dirty && <span className="unsaved-indicator">Unsaved changes</span>}
          <button
            className="button primary"
            disabled={!dirty || save.isPending}
          >
            {save.isPending ? <Spinner /> : <Save size={16} />}Save profile
          </button>
        </PageHead>
        <div className="profile-layout">
          <div className="profile-main">
            <section className="form-section">
              <div className="section-title">
                <h2>
                  <UserRound size={19} />
                  The essentials
                </h2>
                <span className="section-number">01</span>
              </div>
              <div className="form-grid">
                <Field id="full-name" label="Full name">
                  <input
                    id="full-name"
                    value={form.full_name || ""}
                    onChange={(event) => set("full_name", event.target.value)}
                    autoComplete="name"
                    placeholder="Your name"
                  />
                </Field>
                <Field id="headline" label="Professional headline">
                  <input
                    id="headline"
                    value={form.headline || ""}
                    onChange={(event) => set("headline", event.target.value)}
                    placeholder="e.g. Technical Support Engineer"
                  />
                </Field>
                <Field id="experience" label="Years of experience">
                  <input
                    id="experience"
                    type="number"
                    min="0"
                    max="70"
                    step="0.5"
                    value={form.total_years_experience ?? ""}
                    onChange={(event) =>
                      set(
                        "total_years_experience",
                        event.target.value ? Number(event.target.value) : 0,
                      )
                    }
                  />
                </Field>
                <Field id="seniority" label="Experience level">
                  <select
                    id="seniority"
                    value={form.seniority || ""}
                    onChange={(event) => set("seniority", event.target.value)}
                  >
                    <option value="">Not specified</option>
                    {[
                      "intern",
                      "junior",
                      "mid",
                      "senior",
                      "lead",
                      "principal",
                      "director",
                    ].map((level) => (
                      <option key={level} value={level}>
                        {level === "mid"
                          ? "Mid-level"
                          : level[0].toUpperCase() + level.slice(1)}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <Field id="summary" label="Professional summary" optional>
                <textarea
                  id="summary"
                  rows={4}
                  value={form.summary || ""}
                  onChange={(event) => set("summary", event.target.value)}
                  placeholder="Your experience, strengths, and the work you enjoy."
                />
              </Field>
            </section>
            <section className="form-section">
              <div className="section-title">
                <h2>
                  <ShieldCheck size={19} />
                  Skills & expertise
                </h2>
                <span className="section-number">02</span>
              </div>
              <Field id="skills" label="Your skills">
                <TagInput
                  id="skills"
                  values={(form.skills || []).map((skill) => skill.name)}
                  onChange={(names) =>
                    set(
                      "skills",
                      names.map(
                        (name) =>
                          form.skills?.find((skill) => skill.name === name) || {
                            name,
                            core: true,
                            level: "unknown",
                          },
                      ),
                    )
                  }
                  placeholder="Add a skill"
                />
              </Field>
            </section>
            <section className="form-section">
              <div className="section-title">
                <h2>What comes next</h2>
                <span className="section-number">03</span>
              </div>
              <Field id="target-roles" label="Target roles">
                <TagInput
                  id="target-roles"
                  values={form.target_titles || []}
                  onChange={(values) => set("target_titles", values)}
                  placeholder="Add a role"
                />
              </Field>
              <Field id="locations" label="Preferred locations">
                <TagInput
                  id="locations"
                  values={form.locations || []}
                  onChange={(values) => set("locations", values)}
                  placeholder="Add a city or country"
                />
              </Field>
              <fieldset className="choice-field">
                <legend>Working arrangement</legend>
                <div className="choice-options">
                  {[
                    { value: "remote", name: "Remote" },
                    { value: "hybrid", name: "Hybrid" },
                    { value: "onsite", name: "On site" },
                  ].map((option) => (
                    <label key={option.value}>
                      <input
                        type="checkbox"
                        checked={
                          form.work_modes?.includes(option.value) || false
                        }
                        onChange={() => toggle("work_modes", option.value)}
                      />
                      {option.name}
                    </label>
                  ))}
                </div>
              </fieldset>
              <fieldset className="choice-field">
                <legend>Employment type</legend>
                <div className="choice-options">
                  {[
                    { value: "full-time", name: "Full-time" },
                    { value: "part-time", name: "Part-time" },
                    { value: "contract", name: "Contract" },
                    { value: "internship", name: "Internship" },
                  ].map((option) => (
                    <label key={option.value}>
                      <input
                        type="checkbox"
                        checked={
                          form.employment_types?.includes(option.value) || false
                        }
                        onChange={() =>
                          toggle("employment_types", option.value)
                        }
                      />
                      {option.name}
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="form-grid">
                <Field id="recency" label="Posting age">
                  <select
                    id="recency"
                    value={form.recency_days || 14}
                    onChange={(event) =>
                      set("recency_days", Number(event.target.value))
                    }
                  >
                    {[7, 14, 30, 90, 365].map((days) => (
                      <option key={days} value={days}>
                        Last {days} days
                      </option>
                    ))}
                  </select>
                </Field>
                <Field id="authorization" label="Work authorization" optional>
                  <input
                    id="authorization"
                    value={form.work_authorization || ""}
                    onChange={(event) =>
                      set("work_authorization", event.target.value)
                    }
                    placeholder="e.g. Eligible to work in India"
                  />
                </Field>
              </div>
              <Field
                id="exclusions"
                label="Exclude from job titles & companies"
                optional
              >
                <TagInput
                  id="exclusions"
                  values={form.exclusions || []}
                  onChange={(values) => set("exclusions", values)}
                  placeholder="Add an exclusion"
                />
              </Field>
            </section>
            <section className="form-section">
              <div className="section-title">
                <h2>
                  <Link2 size={19} />
                  Portfolio & links
                </h2>
                <span className="section-number">04</span>
              </div>
              <Field
                id="portfolio-links"
                label="Portfolio, LinkedIn, or GitHub"
                optional
              >
                <textarea
                  id="portfolio-links"
                  rows={3}
                  value={(form.links || []).join("\n")}
                  onChange={(event) =>
                    set("links", event.target.value.split("\n").filter(Boolean))
                  }
                  placeholder="https://"
                />
              </Field>
            </section>
            <section className="form-section">
              <div className="section-title">
                <h2>
                  <ShieldCheck size={19} /> Eligibility & priorities
                </h2>
              </div>
              <PreferenceFields
                profile={form}
                onChange={(patch) =>
                  setEdits((current) => ({ ...current, ...patch }))
                }
              />
            </section>
          </div>
          <aside className="profile-aside">
            <div className="profile-progress">
              <div>
                <strong>Profile completeness</strong>
                <span>{completed} / 4</span>
              </div>
              <progress
                aria-label="Profile completeness"
                max="4"
                value={completed}
              />
              <ul>
                {[
                  { done: !!form.full_name, text: "Your name" },
                  { done: !!form.target_titles?.length, text: "Target roles" },
                  { done: !!form.skills?.length, text: "Skills" },
                  { done: !!form.locations?.length, text: "Locations" },
                ].map((item) => (
                  <li key={item.text} className={item.done ? "done" : ""}>
                    <span>{item.done ? <Check size={12} /> : null}</span>
                    {item.text}
                  </li>
                ))}
              </ul>
            </div>
            <section className="documents-section">
              <div className="section-title">
                <h2>Documents</h2>
                <span className="count-badge">{documents.length}</span>
              </div>
              <div
                className={`upload-zone ${dragging ? "dragging" : ""}`}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  if (!upload.isPending)
                    upload.mutate([...event.dataTransfer.files]);
                }}
              >
                {upload.isPending ? (
                  <Spinner />
                ) : (
                  <Upload size={25} strokeWidth={1.5} />
                )}
                <strong>Resume or portfolio</strong>
                <span>PDF, DOCX, TXT, Markdown</span>
                <button
                  type="button"
                  className="button secondary small"
                  disabled={upload.isPending}
                  onClick={() => input.current?.click()}
                >
                  Choose files
                </button>
                <input
                  className="sr-only"
                  ref={input}
                  type="file"
                  multiple
                  accept=".pdf,.docx,.txt,.md,.markdown"
                  aria-label="Upload resume or portfolio"
                  onChange={(event) => {
                    if (event.target.files?.length)
                      upload.mutate([...event.target.files]);
                    event.target.value = "";
                  }}
                />
              </div>
              <div className="document-list">
                {documents.map((document) => (
                  <div className="document-item" key={document.id}>
                    <FileText size={20} />
                    <div>
                      <strong>{document.label}</strong>
                      <p>
                        {document.extract_state === "ok"
                          ? "Ready"
                          : document.extract_state === "failed"
                            ? "Extraction failed"
                            : "Reading document"}
                      </p>
                      <button
                        type="button"
                        className={
                          document.is_primary
                            ? "document-primary"
                            : "text-button"
                        }
                        disabled={!!document.is_primary || primary.isPending}
                        onClick={() => primary.mutate(document.id)}
                      >
                        {document.is_primary
                          ? "Primary resume"
                          : "Make primary"}
                      </button>
                      {document.extract_error && (
                        <p className="error-text">{document.extract_error}</p>
                      )}
                    </div>
                    <IconButton
                      label={`Analyze ${document.label} with AI`}
                      disabled={analyze.isPending || dirty}
                      onClick={() => analyze.mutate(document.id)}
                    >
                      <Sparkles size={15} />
                    </IconButton>
                    <IconButton
                      label={`Remove ${document.label}`}
                      onClick={() => setRemove(document)}
                    >
                      <Trash2 size={15} />
                    </IconButton>
                  </div>
                ))}
              </div>
            </section>
            <div className="local-note">
              <ShieldCheck size={17} />
              <span>Stored on your device</span>
            </div>
          </aside>
        </div>
        <footer className="profile-footer">
          <span>
            {dirty
              ? "You have unsaved changes."
              : "Your profile is up to date."}
          </span>
          <button
            className="button primary"
            disabled={!dirty || save.isPending}
          >
            {save.isPending ? <Spinner /> : <Save size={16} />}Save profile
          </button>
        </footer>
      </form>
      {remove && (
        <Confirm
          title="Remove this document?"
          detail={`${remove.label} will be removed. Your manually edited profile and preferences will be kept.`}
          action="Remove document"
          onClose={() => setRemove(null)}
          onConfirm={async () => {
            await request(`/cvs/${remove.id}`, { method: "DELETE" });
            await refreshWorkspace();
            notify("Document removed.");
          }}
        />
      )}
      {blocker.state === "blocked" && (
        <Confirm
          title="Discard unsaved changes?"
          detail="Your profile has unsaved edits. Leaving now will discard those edits."
          action="Discard changes"
          onClose={() => blocker.reset?.()}
          onConfirm={async () => {
            blocker.proceed?.();
          }}
        />
      )}
    </>
  );
}
