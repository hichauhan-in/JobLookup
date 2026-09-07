import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileDiff } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { request } from "../api";
import { dateLabel } from "../lib/format";
import type { ResumeVersion } from "../types";
import { ErrorState, Field, Spinner } from "./ui";

type VersionDetail = ResumeVersion & {
  markdown: string;
  base_text: string;
  diff: string;
  checks: {
    new_skill_mentions: string[];
    new_numeric_claims: string[];
    requires_review: boolean;
  };
};

export function ResumeHistory({ jobId }: { jobId: number }) {
  const [selected, setSelected] = useState(0);
  const [compare, setCompare] = useState(true);
  const [open, setOpen] = useState(false);
  const versions = useQuery({
    queryKey: ["versions", jobId],
    queryFn: ({ signal }) =>
      request<{ items: ResumeVersion[] }>(`/opportunities/${jobId}/versions`, {
        signal,
      }),
  });
  const versionId = selected || versions.data?.items[0]?.id || 0;
  const detail = useQuery({
    queryKey: ["resume-version", versionId],
    queryFn: ({ signal }) =>
      request<VersionDetail>(`/resume-versions/${versionId}`, { signal }),
    enabled: !!versionId && open,
  });
  return (
    <details
      className="workflow-disclosure version-history"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <FileDiff size={17} />
        Version history & comparison{" "}
        <span className="count-badge">{versions.data?.items.length || 0}</span>
      </summary>
      {versions.isError ? (
        <ErrorState error={versions.error} />
      ) : !versions.data?.items.length ? (
        <p className="muted">No versioned drafts yet.</p>
      ) : (
        <>
          <Field id="resume-version" label="Saved draft">
            <select
              id="resume-version"
              value={versionId}
              onChange={(event) => setSelected(Number(event.target.value))}
            >
              {versions.data.items.map((version) => (
                <option key={version.id} value={version.id}>
                  Version {version.id} /{" "}
                  {version.cv_label || "Original removed"} /{" "}
                  {dateLabel(version.created_at)}
                </option>
              ))}
            </select>
          </Field>
          <div className="button-row">
            <label className="workflow-check">
              <input
                type="checkbox"
                checked={compare}
                onChange={(event) => setCompare(event.target.checked)}
              />
              Compare with original
            </label>
            <a
              className="button secondary small"
              href={`/api/resume-versions/${versionId}/download`}
            >
              <Download size={15} />
              Download this version
            </a>
          </div>
          {detail.isPending ? (
            <Spinner />
          ) : detail.isError ? (
            <ErrorState error={detail.error} />
          ) : (
            detail.data && (
              <>
                {detail.data.checks.requires_review && (
                  <div className="review-notice">
                    <strong>
                      Claims to verify against your original resume
                    </strong>
                    {!!detail.data.checks.new_skill_mentions.length && (
                      <p>
                        New skill mentions:{" "}
                        {detail.data.checks.new_skill_mentions.join(", ")}
                      </p>
                    )}
                    {!!detail.data.checks.new_numeric_claims.length && (
                      <p>
                        New numbers:{" "}
                        {detail.data.checks.new_numeric_claims.join(", ")}
                      </p>
                    )}
                  </div>
                )}
                {compare ? (
                  <pre className="resume-diff">
                    {detail.data.diff.split("\n").map((line, index) => (
                      <span
                        className={
                          line.startsWith("+")
                            ? "diff-added"
                            : line.startsWith("-")
                              ? "diff-removed"
                              : ""
                        }
                        key={index}
                      >
                        {line || " "}
                        {"\n"}
                      </span>
                    ))}
                  </pre>
                ) : (
                  <div className="prose">
                    <ReactMarkdown skipHtml>
                      {detail.data.markdown}
                    </ReactMarkdown>
                  </div>
                )}
              </>
            )
          )}
        </>
      )}
    </details>
  );
}
