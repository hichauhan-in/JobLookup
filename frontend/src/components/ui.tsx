import { useEffect, useRef, useState } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  LoaderCircle,
  SearchX,
  X,
} from "lucide-react";
import { errorMessage } from "../api";
import type { Fit } from "../types";
import { ToastContext } from "./notifications";
import type { Notice } from "./notifications";

export function ToastProvider({ children }: { children: ReactNode }) {
  const [notice, setNotice] = useState<Notice | null>(null);
  const timer = useRef<number>(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const notify = (message: string, tone: Notice["tone"] = "success") => {
    window.clearTimeout(timer.current);
    setNotice({ message, tone });
    timer.current = window.setTimeout(
      () => setNotice(null),
      tone === "error" ? 9000 : 4500,
    );
  };
  return (
    <ToastContext.Provider value={notify}>
      {children}
      {notice && (
        <div
          className={`toast ${notice.tone}`}
          role={notice.tone === "error" ? "alert" : "status"}
        >
          {notice.tone === "error" ? (
            <AlertCircle size={19} />
          ) : (
            <CheckCircle2 size={19} />
          )}
          <span>{notice.message}</span>
          <IconButton
            label="Dismiss notification"
            onClick={() => setNotice(null)}
          >
            <X size={17} />
          </IconButton>
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function IconButton({
  label,
  children,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      className={`icon-button ${className}`}
      title={label}
      aria-label={label}
      {...props}
    >
      {children}
    </button>
  );
}

export function Spinner({ label: name = "Loading" }: { label?: string }) {
  return (
    <LoaderCircle className="spin" size={18} role="status" aria-label={name} />
  );
}

export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={20} />
      <span>{errorMessage(error)}</span>
      {retry && (
        <button className="button secondary small" onClick={retry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  detail,
  children,
}: {
  title: string;
  detail?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <SearchX size={30} strokeWidth={1.4} />
      </div>
      <h2>{title}</h2>
      {detail && <p>{detail}</p>}
      {children && <div className="button-row">{children}</div>}
    </div>
  );
}

export function PageHead({
  eyebrow,
  title,
  detail,
  children,
}: {
  eyebrow?: string;
  title: string;
  detail?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {detail && <p className="page-description">{detail}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  );
}

export function Dialog({
  title,
  children,
  onClose,
  drawer = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  drawer?: boolean;
}) {
  const reference = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = reference.current;
    const previous = document.body.style.overflow;
    element?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      element?.close();
      document.body.style.overflow = previous;
    };
  }, []);
  return (
    <dialog
      ref={reference}
      className={drawer ? "drawer" : "dialog"}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="dialog-inner">
        <header className="dialog-header">
          <h2>{title}</h2>
          <IconButton label="Close dialog" onClick={onClose}>
            <X size={20} />
          </IconButton>
        </header>
        {children}
      </div>
    </dialog>
  );
}

export function Confirm({
  title,
  detail,
  action,
  onClose,
  onConfirm,
}: {
  title: string;
  detail: string;
  action: string;
  onClose: () => void;
  onConfirm: () => Promise<unknown>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  return (
    <Dialog
      title={title}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="dialog-body">
        <p className="confirm-detail">{detail}</p>
        {error != null && <ErrorState error={error} />}
      </div>
      <footer className="dialog-footer">
        <button
          autoFocus
          className="button secondary"
          disabled={busy}
          onClick={onClose}
        >
          Cancel
        </button>
        <button
          className="button danger"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await onConfirm();
              onClose();
            } catch (failure) {
              setError(failure);
              setBusy(false);
            }
          }}
        >
          {busy && <Spinner />}
          {action}
        </button>
      </footer>
    </Dialog>
  );
}

export function FitBadge({ fit }: { fit: Fit }) {
  const names = {
    strong: "Strong fit",
    good: "Good fit",
    review: "Needs review",
    excluded: "Outside preferences",
  };
  return (
    <span className={`fit-badge ${fit.band}`} title={fit.method}>
      {fit.band === "strong" || fit.band === "good" ? (
        <Check size={13} />
      ) : (
        <AlertCircle size={13} />
      )}
      {names[fit.band]}
    </span>
  );
}

export function Field({
  id,
  label,
  children,
  optional,
}: {
  id: string;
  label: string;
  children: ReactNode;
  optional?: boolean;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {optional && <span className="optional">Optional</span>}
      </label>
      {children}
    </div>
  );
}

export function TagInput({
  id,
  values,
  onChange,
  placeholder,
}: {
  id: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");
  const commit = () => {
    const additions = draft
      .split(/[,;\n]/)
      .map((value) => value.trim())
      .filter(Boolean);
    if (additions.length)
      onChange([...new Set([...values, ...additions])].slice(0, 100));
    setDraft("");
  };
  return (
    <div className="tag-input">
      {values.map((value) => (
        <span className="input-tag" key={value}>
          {value}
          <button
            type="button"
            aria-label={`Remove ${value}`}
            title={`Remove ${value}`}
            onClick={() => onChange(values.filter((item) => item !== value))}
          >
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        placeholder={placeholder}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === ",") {
            event.preventDefault();
            commit();
          }
          if (event.key === "Backspace" && !draft)
            onChange(values.slice(0, -1));
        }}
      />
    </div>
  );
}

export function Skeletons({ count = 4 }: { count?: number }) {
  return (
    <div className="job-grid" aria-busy="true" aria-label="Loading matches">
      {Array.from({ length: count }, (_, index) => (
        <div className="job-card skeleton-card" key={index}>
          <div className="skeleton short" />
          <div className="skeleton" />
          <div className="skeleton medium" />
          <div className="skeleton" />
        </div>
      ))}
    </div>
  );
}
