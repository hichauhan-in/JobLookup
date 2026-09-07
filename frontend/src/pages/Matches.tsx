import { useDeferredValue, useState } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  Bookmark,
  BriefcaseBusiness,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  EyeOff,
  History,
  MapPin,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import {
  errorMessage,
  post,
  refreshWorkspace,
  request,
  useWorkspace,
} from "../api";
import { ago, companyColor, initials, label, salary } from "../lib/format";
import type { Opportunities, Opportunity, Sources, Task } from "../types";
import { JobDetails } from "../components/JobDetails";
import {
  Confirm,
  EmptyState,
  ErrorState,
  FitBadge,
  IconButton,
  PageHead,
  Skeletons,
  Spinner,
} from "../components/ui";
import { useToast } from "../components/notifications";

export default function Matches() {
  const [params, setParams] = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const workspace = useWorkspace();
  const notify = useToast();
  const profile = workspace.data?.profile.data;
  const query = params.get("q") || "";
  const deferredQuery = useDeferredValue(query);
  const view = ["recommended", "review", "all", "hidden"].includes(
    params.get("view") || "",
  )
    ? params.get("view")!
    : "recommended";
  const days = Number(
    params.get("days") ||
      profile?.recency_days ||
      workspace.data?.defaults.days ||
      14,
  );
  const mode = params.get("mode") || "all";
  const source = params.get("source") || "";
  const sort = params.get("sort") || "fit";
  const page = Math.max(1, Number(params.get("page") || 1));
  const selectedId = Number(params.get("job") || 0);
  const change = (values: Record<string, string>, resetPage = true) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        Object.entries(values).forEach(([key, value]) =>
          value ? next.set(key, value) : next.delete(key),
        );
        if (resetPage) next.delete("page");
        return next;
      },
      { replace: true },
    );
  const search = new URLSearchParams({
    view,
    query: deferredQuery,
    days: String(days),
    mode,
    source,
    sort,
    page: String(page),
  });
  const matches = useQuery({
    queryKey: ["opportunities", search.toString()],
    queryFn: ({ signal }) =>
      request<Opportunities>(`/opportunities?${search}`, { signal }),
    enabled: workspace.isSuccess,
    placeholderData: keepPreviousData,
  });
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: ({ signal }) => request<Sources>("/sources", { signal }),
    enabled: filtersOpen,
  });
  const discover = useMutation({
    mutationFn: () => post<{ task: Task }>("/discover", { days }),
    onSuccess: async () => {
      notify("Search started.");
      await refreshWorkspace();
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const totals = matches.data?.buckets;
  const isSearching =
    discover.isPending ||
    workspace.data?.tasks.some((task) => task.kind === "search");
  const lastRun = workspace.data?.runs[0];
  const failedSources = Object.keys(lastRun?.stats.failures || {});
  return (
    <>
      <PageHead
        eyebrow="YOUR NEXT CHAPTER"
        title="Your matches"
        detail={
          profile?.target_titles?.length ? (
            <>
              {profile.target_titles.slice(0, 2).join(" / ")}
              <span className="description-separator">·</span>
              {profile.locations?.join(", ") || "Location not set"}
            </>
          ) : (
            "A fresh start for your job search."
          )
        }
      >
        <Link className="button secondary" to="/settings?tab=history">
          <History size={16} />
          History
        </Link>
        <button
          className="button primary"
          disabled={!!isSearching || !profile?.target_titles?.length}
          onClick={() => discover.mutate()}
        >
          {isSearching ? <Spinner /> : <Search size={16} />}
          {isSearching ? "Searching" : "Find jobs"}
        </button>
      </PageHead>
      {workspace.isError && (
        <ErrorState
          error={workspace.error}
          retry={() => void workspace.refetch()}
        />
      )}
      <section className="metrics-strip" aria-label="Match summary">
        <div className="metric">
          <span className="metric-icon green">
            <Sparkles size={18} />
          </span>
          <div>
            <strong>{totals?.recommended ?? "—"}</strong>
            <span>Recommended</span>
          </div>
        </div>
        <div className="metric">
          <span className="metric-icon amber">
            <CircleHelp size={18} />
          </span>
          <div>
            <strong>{totals?.review ?? "—"}</strong>
            <span>Need a closer look</span>
          </div>
        </div>
        <div className="metric">
          <span className="metric-icon blue">
            <Bookmark size={18} />
          </span>
          <div>
            <strong>{workspace.data?.counts.tracked ?? "—"}</strong>
            <span>In your applications</span>
          </div>
        </div>
        <div className="metric">
          <span className="metric-icon neutral">
            <BriefcaseBusiness size={18} />
          </span>
          <div>
            <strong>{matches.data?.scanned ?? "—"}</strong>
            <span>Postings screened</span>
          </div>
        </div>
      </section>
      {failedSources.length > 0 && (
        <div className="inline-notice">
          <CircleHelp size={16} />
          <span>
            Last search: {failedSources.length} source
            {failedSources.length === 1 ? "" : "s"} unavailable.
          </span>
          <Link to="/settings?tab=history">
            View report
            <ArrowRight size={14} />
          </Link>
        </div>
      )}
      <section className="match-workspace">
        <div className="results-toolbar">
          <div className="search-input">
            <Search size={17} />
            <input
              aria-label="Search matches"
              placeholder="Search roles or companies"
              value={query}
              onChange={(event) => change({ q: event.target.value })}
            />
            {query && (
              <IconButton
                label="Clear search"
                onClick={() => change({ q: "" })}
              >
                <X size={15} />
              </IconButton>
            )}
          </div>
          <select
            aria-label="Work arrangement"
            value={mode}
            onChange={(event) => change({ mode: event.target.value })}
          >
            <option value="all">Any work mode</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On site</option>
          </select>
          <select
            aria-label="Posting age"
            value={days}
            onChange={(event) => change({ days: event.target.value })}
          >
            {[7, 14, 30, 90, 365].map((value) => (
              <option key={value} value={value}>
                Last {value} days
              </option>
            ))}
          </select>
          <button
            className={`button secondary filter-button ${filtersOpen ? "selected" : ""}`}
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen(!filtersOpen)}
          >
            <SlidersHorizontal size={16} />
            Filters
          </button>
        </div>
        {filtersOpen && (
          <div className="expanded-filters">
            <label>
              Source
              <select
                value={source}
                onChange={(event) => change({ source: event.target.value })}
              >
                <option value="">Every source</option>
                {sources.data?.sources.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <button className="button text small" onClick={() => setParams({})}>
              <RotateCcw size={14} />
              Reset filters
            </button>
            <Link className="button text small" to="/profile">
              Edit preferences
              <ArrowUpRight size={14} />
            </Link>
          </div>
        )}
        <div className="results-heading">
          <nav className="tabs" aria-label="Match views">
            {[
              { key: "recommended", name: "Recommended" },
              { key: "review", name: "Needs review" },
              { key: "all", name: "All postings" },
            ].map((item) => (
              <button
                key={item.key}
                className={view === item.key ? "active" : ""}
                aria-current={view === item.key ? "page" : undefined}
                onClick={() => change({ view: item.key })}
              >
                {item.name}
                <span>
                  {totals?.[item.key as "recommended" | "review" | "all"] ?? 0}
                </span>
              </button>
            ))}
          </nav>
          <div className="results-tools">
            {matches.isFetching && !matches.isPending && (
              <Spinner label="Updating results" />
            )}
            <select
              className="sort-select"
              aria-label="Sort matches"
              value={sort}
              onChange={(event) => change({ sort: event.target.value })}
            >
              <option value="fit">Best fit first</option>
              <option value="newest">Newest first</option>
              <option value="company">Company A-Z</option>
            </select>
            <IconButton
              label={view === "hidden" ? "Back to recommended" : "Hidden jobs"}
              className={view === "hidden" ? "selected" : ""}
              onClick={() =>
                change({ view: view === "hidden" ? "recommended" : "hidden" })
              }
            >
              <EyeOff size={17} />
            </IconButton>
            <IconButton
              label="Clear stored matches"
              onClick={() => setResetOpen(true)}
            >
              <Trash2 size={17} />
            </IconButton>
          </div>
        </div>
        {view === "hidden" && (
          <p className="section-caption">
            <EyeOff size={15} />
            Hidden jobs
          </p>
        )}
        {workspace.isPending || matches.isPending ? (
          <Skeletons />
        ) : matches.isError ? (
          <ErrorState
            error={matches.error}
            retry={() => void matches.refetch()}
          />
        ) : !matches.data?.has_profile ? (
          <EmptyState
            title="Your profile comes first"
            detail="No target roles have been saved yet."
          >
            <Link className="button primary" to="/profile">
              Create your profile
              <ArrowRight size={16} />
            </Link>
          </EmptyState>
        ) : matches.data.items.length === 0 ? (
          <EmptyState
            title={
              view === "recommended"
                ? "No verified matches yet"
                : "Nothing in this view"
            }
            detail={
              view === "recommended" && totals?.review
                ? `${totals.review} postings have details that still need confirmation.`
                : "No stored jobs meet this selection."
            }
          >
            {view === "recommended" && !!totals?.review && (
              <button
                className="button primary"
                onClick={() => change({ view: "review" })}
              >
                Review those postings
                <ArrowRight size={16} />
              </button>
            )}
            <button
              className="button secondary"
              onClick={() => setParams({ view: "all", days: "365" })}
            >
              All stored postings
            </button>
          </EmptyState>
        ) : (
          <div
            className={`job-grid ${matches.isPlaceholderData ? "updating" : ""}`}
            aria-busy={matches.isFetching}
          >
            {matches.data.items.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                onOpen={() => change({ job: String(job.id) }, false)}
              />
            ))}
          </div>
        )}
        {!!matches.data?.total && (
          <footer className="pagination">
            <span>
              {(page - 1) * 20 + 1}-{Math.min(page * 20, matches.data.total)} of{" "}
              {matches.data.total} postings
            </span>
            <div className="button-row">
              <IconButton
                label="Previous page"
                disabled={page <= 1}
                onClick={() => change({ page: String(page - 1) }, false)}
              >
                <ChevronLeft size={18} />
              </IconButton>
              <span>Page {page}</span>
              <IconButton
                label="Next page"
                disabled={page * 20 >= matches.data.total}
                onClick={() => change({ page: String(page + 1) }, false)}
              >
                <ChevronRight size={18} />
              </IconButton>
            </div>
          </footer>
        )}
      </section>
      {selectedId > 0 && (
        <JobDetails
          id={selectedId}
          onClose={() => change({ job: "" }, false)}
        />
      )}
      {resetOpen && (
        <Confirm
          title="Clear stored matches?"
          detail="Untracked postings and their scores will be deleted. Your applications, resumes, profile, and search history will be kept."
          action="Clear matches"
          onClose={() => setResetOpen(false)}
          onConfirm={async () => {
            await post("/opportunities/reset");
            await refreshWorkspace();
            notify("Untracked matches cleared.");
          }}
        />
      )}
    </>
  );
}

function JobCard({ job, onOpen }: { job: Opportunity; onOpen: () => void }) {
  const notify = useToast();
  const mutate = useMutation({
    mutationFn: (action: "save" | "hide") =>
      action === "save"
        ? post(`/jobs/${job.id}/application`, { status: "saved" })
        : post(`/jobs/${job.id}/hide?hidden=${!job.hidden}`),
    onSuccess: async (_, action) => {
      notify(
        action === "save"
          ? "Added to your applications."
          : job.hidden
            ? "Job restored."
            : "Job hidden.",
      );
      await refreshWorkspace();
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  return (
    <article
      className={`job-card ${job.fit.band === "excluded" ? "excluded-card" : ""}`}
    >
      <div className="job-card-top">
        <div className="company-heading">
          <div className={`company-avatar color-${companyColor(job.company)}`}>
            {initials(job.company)}
          </div>
          <div>
            <strong>{job.company}</strong>
            <span>{ago(job.posted_at)}</span>
          </div>
        </div>
        <IconButton
          label={
            job.application_status
              ? "Saved to applications"
              : `Save ${job.title}`
          }
          className={job.application_status ? "bookmarked" : ""}
          disabled={!!job.application_status || mutate.isPending}
          onClick={() => mutate.mutate("save")}
        >
          {job.application_status ? (
            <Bookmark size={19} fill="currentColor" />
          ) : (
            <Bookmark size={19} />
          )}
        </IconButton>
      </div>
      <button className="job-title" onClick={onOpen}>
        {job.title}
      </button>
      <div className="job-meta">
        <span>
          <MapPin size={14} />
          {job.location || "Location unknown"}
        </span>
        <span>
          <BriefcaseBusiness size={14} />
          {label(job.work_mode)}
        </span>
      </div>
      {salary(job.salary_min, job.salary_max, job.salary_currency) && (
        <div className="job-pay">
          {salary(job.salary_min, job.salary_max, job.salary_currency)}
        </div>
      )}
      <div className="match-explanation">
        <span className={`fit-score ${job.fit.band}`}>
          {job.fit.score}
          <small>fit</small>
        </span>
        <div>
          <FitBadge fit={job.fit} />
          <p>{job.fit.summary}</p>
        </div>
      </div>
      <div className="skill-tags">
        {job.fit.matched_skills.slice(0, 3).map((entry) => (
          <span className="matched" key={entry.skill}>
            <Check size={11} />
            {entry.skill}
          </span>
        ))}
        {job.fit.matched_skills.length > 3 && (
          <span>+{job.fit.matched_skills.length - 3}</span>
        )}
        {!job.fit.matched_skills.length && (
          <span className="unverified">
            <CircleHelp size={12} />
            Skill evidence limited
          </span>
        )}
      </div>
      <footer className="job-card-footer">
        <span className="source-name">
          <Clock3 size={13} />
          {label(job.source_keys?.filter(Boolean)[0])}
          {job.source_keys?.length > 1 ? ` +${job.source_keys.length - 1}` : ""}
        </span>
        <div>
          <IconButton
            label={job.hidden ? `Restore ${job.title}` : `Hide ${job.title}`}
            disabled={mutate.isPending}
            onClick={() => mutate.mutate("hide")}
          >
            {job.hidden ? <RotateCcw size={15} /> : <EyeOff size={15} />}
          </IconButton>
          <button className="view-match" onClick={onOpen}>
            View match
            <ArrowUpRight size={15} />
          </button>
        </div>
      </footer>
    </article>
  );
}
