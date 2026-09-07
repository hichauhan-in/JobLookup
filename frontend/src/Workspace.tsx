import { Component, lazy, Suspense, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Link,
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
  useParams,
} from "react-router-dom";
import {
  ArrowUpRight,
  BriefcaseBusiness,
  ChevronRight,
  Compass,
  FolderClosed,
  Menu,
  ScanSearch,
  Settings2,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";
import {
  errorMessage,
  post,
  queryClient,
  refreshWorkspace,
  request,
  useWorkspace,
} from "./api";
import { initials } from "./lib/format";
import type { Task } from "./types";
import { ErrorState, IconButton, Skeletons, Spinner } from "./components/ui";
import { useToast } from "./components/notifications";

const Matches = lazy(() => import("./pages/Matches"));
const Applications = lazy(() => import("./pages/Applications"));
const Profile = lazy(() => import("./pages/Profile"));
const Settings = lazy(() => import("./pages/Settings"));

export default function Workspace() {
  const [menuOpen, setMenuOpen] = useState(false);
  const workspace = useWorkspace();
  const location = useLocation();
  const profile = workspace.data?.profile.data;
  const names: Record<string, string> = {
    matches: "Matches",
    applications: "Applications",
    profile: "Your profile",
    settings: "Settings",
  };
  const page = names[location.pathname.split("/")[1]] || "Matches";
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        Skip to content
      </a>
      {menuOpen && (
        <button
          className="nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside className={`sidebar ${menuOpen ? "is-open" : ""}`}>
        <Link
          to="/matches"
          className="brand"
          onClick={() => setMenuOpen(false)}
        >
          <span className="brand-mark">
            <ScanSearch size={23} strokeWidth={1.7} />
          </span>
          <span>
            JobLookup<span className="brand-period">.</span>
          </span>
        </Link>
        <div className="sidebar-workspace">
          <FolderClosed size={15} />
          <span>Personal workspace</span>
          <span className="workspace-initial">P</span>
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav className="main-nav" aria-label="Main navigation">
          <NavLink to="/matches" onClick={() => setMenuOpen(false)}>
            <Compass size={18} />
            <span>Matches</span>
          </NavLink>
          <NavLink to="/applications" onClick={() => setMenuOpen(false)}>
            <BriefcaseBusiness size={18} />
            <span>Applications</span>
            {!!workspace.data?.counts.tracked && (
              <span className="nav-count">{workspace.data.counts.tracked}</span>
            )}
          </NavLink>
          <NavLink to="/profile" onClick={() => setMenuOpen(false)}>
            <UserRound size={18} />
            <span>Your profile</span>
          </NavLink>
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace-health">
            <ShieldCheck size={17} />
            <div>
              <strong>Local workspace</strong>
              <span>
                {workspace.isError ? "Server unavailable" : "On this device"}
              </span>
            </div>
          </div>
          <nav className="main-nav" aria-label="Workspace settings">
            <NavLink to="/settings" onClick={() => setMenuOpen(false)}>
              <Settings2 size={18} />
              <span>Settings</span>
            </NavLink>
          </nav>
          <Link
            to="/profile"
            className="sidebar-profile"
            onClick={() => setMenuOpen(false)}
          >
            <span className="user-avatar">
              {initials(profile?.full_name || "")}
            </span>
            <span>
              <strong>{profile?.full_name || "Your profile"}</strong>
              <small>{profile?.headline || "Personal job search"}</small>
            </span>
            <ChevronRight size={15} />
          </Link>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <IconButton
              label="Open navigation"
              className="mobile-menu"
              onClick={() => setMenuOpen(!menuOpen)}
            >
              <Menu size={21} />
            </IconButton>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{page}</strong>
          </div>
          <div className="topbar-actions">
            <span
              className={`local-status ${workspace.isError ? "unavailable" : ""}`}
            >
              <span className="status-dot" />
              {workspace.isPending
                ? "Connecting"
                : workspace.isError
                  ? "Server unavailable"
                  : "Local matching active"}
            </span>
            <Link className="connection-link" to="/settings?tab=connection">
              AI connection
              <ArrowUpRight size={14} />
            </Link>
          </div>
        </header>
        <TaskMonitor />
        <main id="main" tabIndex={-1} className="main-content">
          <ViewBoundary>
            <Suspense fallback={<Skeletons />}>
              <Routes>
                <Route path="/matches" element={<Matches />} />
                <Route path="/applications" element={<Applications />} />
                <Route path="/profile" element={<Profile />} />
                <Route path="/settings" element={<Settings />} />
                <Route
                  path="/sources"
                  element={<Navigate to="/settings?tab=sources" replace />}
                />
                <Route
                  path="/history"
                  element={<Navigate to="/settings?tab=history" replace />}
                />
                <Route path="/job/:id" element={<LegacyJob />} />
                <Route path="*" element={<Navigate to="/matches" replace />} />
              </Routes>
            </Suspense>
          </ViewBoundary>
        </main>
        <footer className="workspace-footer">
          <span>JobLookup</span>
          <span>Personal workspace</span>
        </footer>
      </div>
    </div>
  );
}

function LegacyJob() {
  const { id } = useParams();
  return <Navigate replace to={`/matches?job=${id}`} />;
}

function TaskMonitor() {
  const previous = useRef(new Map<string, string>());
  const notify = useToast();
  const tasks = useQuery({
    queryKey: ["tasks"],
    queryFn: ({ signal }) =>
      request<{ active: Task[]; recent: Task[] }>("/tasks", { signal }),
    refetchInterval: (query) =>
      query.state.data?.active.length ? 1000 : 10_000,
  });
  const cancel = useMutation({
    mutationFn: (id: string) => post(`/tasks/${id}/cancel`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks"] }),
    onError: (error) => notify(errorMessage(error), "error"),
  });
  useEffect(() => {
    for (const task of tasks.data?.recent || []) {
      const wasActive = ["running", "queued"].includes(
        previous.current.get(task.id) || "",
      );
      previous.current.set(task.id, task.status);
      if (!wasActive || ["running", "queued"].includes(task.status)) continue;
      void refreshWorkspace();
      void queryClient.invalidateQueries({ queryKey: ["history"] });
      if (["sign-in", "test-selectors", "provision"].includes(task.kind)) {
        void queryClient.invalidateQueries({ queryKey: ["portals"] });
        void queryClient.invalidateQueries({ queryKey: ["sources"] });
      }
      if (task.status === "failed")
        notify(task.error || `${task.label} failed.`, "error");
      else if (task.status === "cancelled") notify("Task stopped.");
      else notify(`${task.label} completed.`);
    }
  }, [tasks.data, notify]);
  const active = tasks.data?.active[0];
  if (!active) return null;
  return (
    <section className="task-strip" aria-live="polite">
      <Spinner />
      <div className="task-message">
        <strong>{active.label}</strong>
        <span>{active.message || "Queued"}</span>
      </div>
      <progress
        aria-label="Task progress"
        max={1}
        value={
          active.fraction != null && active.fraction < 1
            ? active.fraction
            : undefined
        }
      />
      <span className="task-time">{Math.floor(active.elapsed)}s</span>
      <IconButton
        label="Stop task"
        disabled={cancel.isPending}
        onClick={() => cancel.mutate(active.id)}
      >
        <X size={17} />
      </IconButton>
    </section>
  );
}

class ViewBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    return this.state.error ? (
      <ErrorState
        error={
          new Error(
            "This view could not be opened. Reload the workspace to try again.",
          )
        }
        retry={() => window.location.reload()}
      />
    ) : (
      this.props.children
    );
  }
}
