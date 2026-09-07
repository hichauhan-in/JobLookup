import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Download,
  FlaskConical,
  HardDriveDownload,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { downloadFile, errorMessage, queryClient, request } from "../api";
import { dateLabel, label } from "../lib/format";
import { Dialog, ErrorState, Field, Spinner } from "./ui";
import { useToast } from "./notifications";

type Benchmark = {
  sample_size: number;
  relevant: number;
  false_exclusions: number;
  top20_labeled_relevant: number;
  top20_labeled_count: number;
  needs_review: number;
  results: {
    job_id: number;
    track_id: number;
    title: string;
    label: string;
    score: number;
    band: string;
  }[];
};
type BackupPreview = {
  sha256: string;
  created_at: string;
  counts: Record<string, number>;
  documents: number;
  missing_files: number;
};

export function WorkspaceTools() {
  const benchmark = useQuery({
    queryKey: ["benchmark"],
    queryFn: ({ signal }) => request<Benchmark>("/benchmark", { signal }),
  });
  return (
    <>
      <section className="workflow-section spaced-section">
        <div className="section-title">
          <h2>
            <FlaskConical size={18} />
            Relevance benchmark
          </h2>
          <a className="button secondary small" href="/api/benchmark/export">
            <Download size={15} />
            Export labels
          </a>
        </div>
        {benchmark.isPending ? (
          <Spinner />
        ) : benchmark.isError ? (
          <ErrorState error={benchmark.error} />
        ) : (
          <>
            <div className="workflow-stat-strip">
              <div>
                <strong>{benchmark.data.sample_size}</strong>
                <span>Labeled postings</span>
              </div>
              <div>
                <strong>
                  {benchmark.data.top20_labeled_relevant} /{" "}
                  {benchmark.data.top20_labeled_count}
                </strong>
                <span>Relevant in labeled top 20</span>
              </div>
              <div>
                <strong>{benchmark.data.false_exclusions}</strong>
                <span>Relevant jobs excluded</span>
              </div>
            </div>
            <p className="section-caption">
              User-labeled sample only; not accuracy across all jobs. Profile
              evidence and posting age are preserved at labeling time.
            </p>
            {!!benchmark.data.results.length && (
              <div className="workflow-table-scroll">
                <table className="workflow-table">
                  <thead>
                    <tr>
                      <th>Posting</th>
                      <th>Your label</th>
                      <th>Current result</th>
                      <th>Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {benchmark.data.results.slice(0, 30).map((row) => (
                      <tr key={`${row.job_id}-${row.track_id}`}>
                        <td>{row.title}</td>
                        <td>{label(row.label)}</td>
                        <td>{label(row.band)}</td>
                        <td>{row.score}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
      <BackupTools />
      <section className="workflow-section">
        <h2>Browser capture</h2>
        <p className="section-caption">
          The optional Chrome/Edge helper uses active-tab access only. No
          cookies, account credentials, or background browsing.
        </p>
        <a className="button secondary small" href="/api/capture/extension">
          <Download size={15} />
          Download browser helper
        </a>
      </section>
    </>
  );
}

function BackupTools() {
  const [file, setFile] = useState<File | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const notify = useToast();
  const download = useMutation({
    mutationFn: () =>
      downloadFile("/backups/export", "joblookup-workspace.zip"),
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const preview = useMutation({
    mutationFn: () => {
      const body = new FormData();
      body.append("file", file!);
      return request<BackupPreview>("/backups/preview", {
        method: "POST",
        body,
      });
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const restore = useMutation({
    mutationFn: () => {
      const body = new FormData();
      body.append("file", file!);
      body.append("confirmation", confirmation);
      body.append("sha256", preview.data!.sha256);
      return request<{ safety_backup: string }>("/backups/restore", {
        method: "POST",
        body,
      });
    },
    onSuccess: async (result) => {
      setConfirmOpen(false);
      setFile(null);
      preview.reset();
      setConfirmation("");
      await queryClient.invalidateQueries();
      notify(
        `Workspace restored. Schedules paused. Safety backup: ${result.safety_backup}`,
      );
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  return (
    <section className="workflow-section">
      <div className="section-title">
        <h2>
          <HardDriveDownload size={18} />
          Backup & restore
        </h2>
        <button
          className="button secondary small"
          disabled={download.isPending}
          onClick={() => download.mutate()}
        >
          {download.isPending ? <Spinner /> : <Download size={15} />}Export
          workspace
        </button>
      </div>
      <p className="section-caption">
        <ShieldCheck size={15} />
        Documents, profiles, jobs and application history. Connection settings
        and browser sessions are excluded. Backup files contain personal data.
      </p>
      <div className="workflow-form">
        <Field id="backup-file" label="Workspace backup">
          <input
            id="backup-file"
            type="file"
            accept=".zip"
            onChange={(event) => {
              setFile(event.target.files?.[0] || null);
              preview.reset();
              setConfirmation("");
            }}
          />
        </Field>
        <button
          className="button secondary small align-start"
          disabled={!file || preview.isPending}
          onClick={() => preview.mutate()}
        >
          {preview.isPending ? <Spinner /> : <Upload size={15} />}Preview backup
        </button>
        {preview.isError && <ErrorState error={preview.error} />}
        {preview.data && (
          <>
            <dl className="backup-summary">
              <dt>Created</dt>
              <dd>{dateLabel(preview.data.created_at)}</dd>
              <dt>Postings</dt>
              <dd>{preview.data.counts.job}</dd>
              <dt>Applications</dt>
              <dd>{preview.data.counts.application}</dd>
              <dt>Documents</dt>
              <dd>{preview.data.documents}</dd>
              <dt>Search tracks</dt>
              <dd>{preview.data.counts.search_track}</dd>
            </dl>
            {preview.data.missing_files > 0 && (
              <p className="error-text">
                {preview.data.missing_files} original files were unavailable
                when this backup was made.
              </p>
            )}
            <button
              className="button danger align-start"
              onClick={() => setConfirmOpen(true)}
            >
              Restore this backup
            </button>
          </>
        )}
      </div>
      {confirmOpen && (
        <Dialog
          title="Replace this workspace?"
          onClose={() => !restore.isPending && setConfirmOpen(false)}
        >
          <form
            onSubmit={(event) => {
              event.preventDefault();
              restore.mutate();
            }}
          >
            <div className="dialog-body workflow-form">
              <p>
                This replaces profiles, postings, resumes, tracks and
                application history with the previewed backup. A safety backup
                is created first. Existing connection credentials are kept and
                restored schedules are paused.
              </p>
              <Field id="restore-confirmation" label="Type RESTORE to confirm">
                <input
                  id="restore-confirmation"
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  autoComplete="off"
                />
              </Field>
              {restore.isError && <ErrorState error={restore.error} />}
            </div>
            <footer className="dialog-footer">
              <button
                type="button"
                className="button secondary"
                disabled={restore.isPending}
                onClick={() => setConfirmOpen(false)}
              >
                Cancel
              </button>
              <button
                className="button danger"
                disabled={confirmation !== "RESTORE" || restore.isPending}
              >
                {restore.isPending ? <Spinner /> : <Upload size={16} />}Replace
                workspace
              </button>
            </footer>
          </form>
        </Dialog>
      )}
    </section>
  );
}
