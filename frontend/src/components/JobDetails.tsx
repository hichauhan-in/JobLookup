import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Bookmark,
  Check,
  CircleHelp,
  FileDown,
  FileText,
  MapPin,
  ShieldCheck,
  Sparkles,
  XCircle,
  RefreshCw,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  errorMessage,
  post,
  queryClient,
  refreshWorkspace,
  request,
} from "../api";
import { ago, companyColor, initials, label, salary } from "../lib/format";
import type { Feedback, Opportunity, Resume, Review, Task } from "../types";
import { Dialog, ErrorState, FitBadge, IconButton, Spinner } from "./ui";
import { useToast } from "./notifications";
import { RelevanceFeedback } from "./RelevanceFeedback";
import { ResumeHistory } from "./ResumeHistory";

type DetailResponse = {
  job: Opportunity;
  review: Review | null;
  feedback?: Feedback | null;
};
type TailoredResponse = {
  cvs: Resume[];
  tailored?: {
    cv_id: number;
    markdown: string;
    prep_markdown?: string;
    docx_path?: string;
  };
};

export function JobDetails({
  id,
  onClose,
  trackId = 0,
  defaultCv,
}: {
  id: number;
  onClose: () => void;
  trackId?: number;
  defaultCv?: number | null;
}) {
  const [tab, setTab] = useState("overview");
  const [baseCv, setBaseCv] = useState<number | null>(defaultCv || null);
  const notify = useToast();
  const detail = useQuery({
    queryKey: ["opportunity", id, trackId],
    queryFn: ({ signal }) =>
      request<DetailResponse>(`/opportunities/${id}?track_id=${trackId}`, {
        signal,
      }),
  });
  const documents = useQuery({
    queryKey: ["opportunity", id, "documents"],
    queryFn: ({ signal }) =>
      request<TailoredResponse>(`/jobs/${id}`, { signal }),
    enabled: tab === "resume",
  });
  const save = useMutation({
    mutationFn: () => post(`/jobs/${id}/application`, { status: "saved" }),
    onSuccess: async () => {
      notify("Added to your applications.");
      await refreshWorkspace();
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const action = useMutation({
    mutationFn: (kind: "review" | "tailor") =>
      kind === "review"
        ? post<{ task: Task }>(`/opportunities/${id}/review`, {
            track_id: trackId,
          })
        : post<{ task: Task }>(`/jobs/${id}/tailor`, { cv_id: baseCv }),
    onSuccess: async () => {
      notify("AI request started.");
      await refreshWorkspace();
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const job = detail.data?.job;
  const jobId = job?.id;
  useEffect(() => {
    if (!jobId) return;
    void post("/inbox/seen", { job_ids: [jobId], track_id: trackId })
      .then(() =>
        queryClient.invalidateQueries({ queryKey: ["opportunities"] }),
      )
      .catch(() => {});
  }, [jobId, trackId]);
  const check = useMutation({
    mutationFn: () => post(`/opportunities/${id}/check`),
    onSuccess: async () => {
      await refreshWorkspace();
      notify("Public availability check started.");
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const tabs = [
    { id: "overview", name: "Overview" },
    { id: "evidence", name: "Fit evidence" },
    { id: "review", name: "AI review" },
    { id: "resume", name: "Resume" },
  ];
  return (
    <Dialog title="Opportunity details" drawer onClose={onClose}>
      {detail.isPending ? (
        <div className="detail-loading">
          <Spinner />
        </div>
      ) : detail.isError ? (
        <div className="dialog-body">
          <ErrorState
            error={detail.error}
            retry={() => void detail.refetch()}
          />
        </div>
      ) : (
        job && (
          <>
            <div className="detail-intro">
              <div className="company-heading">
                <div
                  className={`company-avatar color-${companyColor(job.company)}`}
                >
                  {initials(job.company)}
                </div>
                <div>
                  <strong>{job.company}</strong>
                  <p>{ago(job.posted_at)}</p>
                </div>
              </div>
              <h1>{job.title}</h1>
              <div className="job-meta">
                <span>
                  <MapPin size={15} />
                  {job.location || "Location not published"}
                </span>
                <span>{label(job.work_mode)}</span>
                <span>{label(job.employment)}</span>
              </div>
              {salary(job.salary_min, job.salary_max, job.salary_currency) && (
                <p className="salary-text">
                  {salary(job.salary_min, job.salary_max, job.salary_currency)}
                </p>
              )}
              <div className="button-row">
                <a
                  className={`button primary ${!job.apply_url && !job.url ? "disabled" : ""}`}
                  href={job.apply_url || job.url || undefined}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  Original posting
                  <ArrowUpRight size={16} />
                </a>
                <button
                  className="button secondary"
                  disabled={save.isPending || !!job.application_status}
                  onClick={() => save.mutate()}
                >
                  {save.isPending ? (
                    <Spinner />
                  ) : job.application_status ? (
                    <Check size={16} />
                  ) : (
                    <Bookmark size={16} />
                  )}
                  {job.application_status
                    ? label(job.application_status)
                    : "Save job"}
                </button>
              </div>
            </div>
            <nav className="tabs detail-tabs" aria-label="Job details">
              {tabs.map((item) => (
                <button
                  key={item.id}
                  className={tab === item.id ? "active" : ""}
                  aria-current={tab === item.id ? "page" : undefined}
                  onClick={() => setTab(item.id)}
                >
                  {item.name}
                </button>
              ))}
            </nav>
            <div className="detail-content">
              {tab === "overview" && (
                <>
                  <div className={`fit-summary ${job.fit.band}`}>
                    <div>
                      <FitBadge fit={job.fit} />
                      <p>{job.fit.summary}</p>
                    </div>
                    <div className="fit-number">
                      {job.fit.score}
                      <span>/ 100</span>
                    </div>
                  </div>
                  {job.fit.blockers.length > 0 && (
                    <div className="fact-notice warning">
                      <XCircle size={17} />
                      <div>
                        <strong>Outside your preferences</strong>
                        {job.fit.blockers.map((reason) => (
                          <p key={reason}>{reason}</p>
                        ))}
                      </div>
                    </div>
                  )}
                  <RelevanceFeedback
                    key={`${id}-${trackId}-${detail.data?.feedback?.label || "none"}`}
                    jobId={id}
                    trackId={trackId}
                    initial={detail.data?.feedback}
                  />
                  <div className="availability-row">
                    <div>
                      <strong>
                        {job.availability === "closed"
                          ? "Posting closed"
                          : job.availability === "listed"
                            ? "Public listing found"
                            : "Availability unverified"}
                      </strong>
                      <p>
                        {job.availability_detail ||
                          "No public availability check yet."}
                      </p>
                      {job.checked_at && (
                        <small>
                          Checked {ago(job.checked_at).toLowerCase()}
                        </small>
                      )}
                    </div>
                    <IconButton
                      label="Check posting availability"
                      disabled={check.isPending}
                      onClick={() => check.mutate()}
                    >
                      <RefreshCw size={16} />
                    </IconButton>
                  </div>
                  <h2 className="section-heading">About the role</h2>
                  <div className="prose">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
                      {job.description ||
                        "The source did not publish a full description."}
                    </ReactMarkdown>
                  </div>
                  <section className="source-proof">
                    <h3>Posting sources</h3>
                    {(job.sources || []).map((source) => (
                      <a
                        key={source.source_key}
                        href={source.url || undefined}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        {label(source.source_key)}
                        <ArrowUpRight size={14} />
                      </a>
                    ))}
                    <p>Last seen {ago(job.last_seen_at).toLowerCase()}</p>
                  </section>
                </>
              )}
              {tab === "evidence" && (
                <>
                  <div className="section-title">
                    <div>
                      <p className="eyebrow">PROFILE ALIGNMENT</p>
                      <h2>Your fit breakdown</h2>
                    </div>
                    <div className="fit-number">
                      {job.fit.score}
                      <span>/ 100</span>
                    </div>
                  </div>
                  <p className="muted small">{job.fit.method}</p>
                  <div className="criteria-list">
                    {job.fit.criteria.map((criterion) => (
                      <div className="criterion" key={criterion.key}>
                        <div className={`criterion-icon ${criterion.state}`}>
                          {criterion.state === "match" ? (
                            <Check size={16} />
                          ) : criterion.state === "mismatch" ? (
                            <XCircle size={16} />
                          ) : (
                            <CircleHelp size={16} />
                          )}
                        </div>
                        <div>
                          <strong>{criterion.label}</strong>
                          <p>{criterion.detail}</p>
                        </div>
                        <span>
                          {criterion.maximum > 0 ? (
                            <>
                              {criterion.points}
                              <small> / {criterion.maximum}</small>
                            </>
                          ) : (
                            label(criterion.state)
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                  {job.fit.warnings.length > 0 && (
                    <section className="review-notice">
                      <h3>
                        <CircleHelp size={17} />
                        Still to confirm
                      </h3>
                      <ul>
                        {job.fit.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
                    </section>
                  )}
                  <h3 className="section-heading">
                    Skills evidenced in the posting
                  </h3>
                  {job.fit.matched_skills.length ? (
                    job.fit.matched_skills.map((entry) => (
                      <details className="evidence-item" key={entry.skill}>
                        <summary>
                          <ShieldCheck size={15} />
                          {entry.skill}
                          {entry.importance && (
                            <span
                              className={`requirement-label ${entry.importance}`}
                            >
                              {label(entry.importance)}
                            </span>
                          )}
                        </summary>
                        <blockquote>{entry.quote}</blockquote>
                      </details>
                    ))
                  ) : (
                    <p className="muted">No explicit skill evidence found.</p>
                  )}
                  {job.fit.other_skills.length > 0 && (
                    <section className="spaced-section">
                      <h3>Other skills mentioned</h3>
                      <div className="skill-tags">
                        {job.fit.other_skills.map((skill) => (
                          <span key={skill}>{skill}</span>
                        ))}
                      </div>
                    </section>
                  )}
                  {job.fit.requirements
                    ?.filter((entry) => entry.importance === "required")
                    .map((entry) => (
                      <details
                        className="evidence-item missing-requirement"
                        key={entry.skill}
                      >
                        <summary>
                          <CircleHelp size={15} />
                          {entry.skill}
                          <span className="requirement-label required">
                            Required, not in profile
                          </span>
                        </summary>
                        <blockquote>{entry.quote}</blockquote>
                      </details>
                    ))}
                </>
              )}
              {tab === "review" && (
                <>
                  <div className="section-title">
                    <h2>AI review</h2>
                    <button
                      className="button secondary small"
                      disabled={action.isPending}
                      onClick={() => action.mutate("review")}
                    >
                      <Sparkles size={15} />
                      {detail.data?.review ? "Review again" : "Request review"}
                    </button>
                  </div>
                  {detail.data?.review ? (
                    <div className="ai-review">
                      <span className="eyebrow">
                        {label(detail.data.review.provider)} · AI-GENERATED
                      </span>
                      <p>{detail.data.review.summary}</p>
                      {detail.data.review.evidence.map((entry) => (
                        <div className="review-evidence" key={entry.skill}>
                          <strong>{entry.skill}</strong>
                          <blockquote>{entry.quote}</blockquote>
                        </div>
                      ))}
                      {detail.data.review.questions.length > 0 && (
                        <>
                          <h3>Questions for the employer</h3>
                          <ul>
                            {detail.data.review.questions.map((question) => (
                              <li key={question}>{question}</li>
                            ))}
                          </ul>
                        </>
                      )}
                    </div>
                  ) : (
                    <div className="quiet-empty">
                      <Sparkles size={28} strokeWidth={1.3} />
                      <h3>Not reviewed by AI</h3>
                      <p>Local evidence score: {job.fit.score} / 100</p>
                    </div>
                  )}
                  {action.isError && <ErrorState error={action.error} />}
                </>
              )}
              {tab === "resume" && (
                <>
                  <div className="section-title">
                    <h2>Tailored resume</h2>
                    <FileText size={21} className="muted" />
                  </div>
                  {documents.isPending ? (
                    <Spinner />
                  ) : documents.isError ? (
                    <ErrorState error={documents.error} />
                  ) : (
                    <>
                      <div className="resume-actions">
                        <label htmlFor="tailor-base">Base document</label>
                        <select
                          id="tailor-base"
                          value={
                            baseCv ||
                            documents.data?.cvs.find((cv) => cv.is_primary)
                              ?.id ||
                            documents.data?.cvs[0]?.id ||
                            ""
                          }
                          onChange={(event) =>
                            setBaseCv(Number(event.target.value))
                          }
                        >
                          {!documents.data?.cvs.length && (
                            <option value="">No resume uploaded</option>
                          )}
                          {documents.data?.cvs.map((cv) => (
                            <option key={cv.id} value={cv.id}>
                              {cv.label}
                            </option>
                          ))}
                        </select>
                        <button
                          className="button primary"
                          disabled={
                            action.isPending || !documents.data?.cvs.length
                          }
                          onClick={() => action.mutate("tailor")}
                        >
                          <Sparkles size={16} />
                          {documents.data?.tailored?.markdown
                            ? "Generate new draft"
                            : "Generate draft"}
                        </button>
                      </div>
                      {documents.data?.tailored?.markdown ? (
                        <>
                          <div className="download-row">
                            <a
                              className="button secondary small"
                              href={`/api/jobs/${id}/tailor/download?cv_id=${documents.data.tailored.cv_id}&kind=markdown`}
                            >
                              <FileDown size={15} />
                              Markdown
                            </a>
                            {documents.data.tailored.docx_path && (
                              <a
                                className="button secondary small"
                                href={`/api/jobs/${id}/tailor/download?cv_id=${documents.data.tailored.cv_id}&kind=docx`}
                              >
                                <FileDown size={15} />
                                Word document
                              </a>
                            )}
                            <a
                              className="button secondary small"
                              href={`/api/jobs/${id}/tailor/download?cv_id=${documents.data.tailored.cv_id}&kind=prep`}
                            >
                              <FileDown size={15} />
                              Interview prep
                            </a>
                          </div>
                          <div className="prose resume-preview">
                            <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
                              {documents.data.tailored.markdown}
                            </ReactMarkdown>
                          </div>
                        </>
                      ) : (
                        <div className="quiet-empty">
                          <FileText size={28} strokeWidth={1.3} />
                          <h3>No tailored draft yet</h3>
                          <p>
                            {documents.data?.cvs.length
                              ? "AI-generated drafts require your review before use."
                              : "No resume is available in your profile."}
                          </p>
                        </div>
                      )}
                    </>
                  )}
                  <ResumeHistory jobId={id} />
                </>
              )}
            </div>
          </>
        )
      )}
    </Dialog>
  );
}
