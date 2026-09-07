import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  CornerUpRight,
  Save,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from "lucide-react";
import { Link } from "react-router-dom";
import { errorMessage, post, refreshWorkspace, request } from "../api";
import type { Feedback } from "../types";
import { Field, IconButton, Spinner } from "./ui";
import { useToast } from "./notifications";

export function RelevanceFeedback({
  jobId,
  trackId,
  initial,
}: {
  jobId: number;
  trackId: number;
  initial?: Feedback | null;
}) {
  const [form, setForm] = useState<Feedback>(
    initial || { label: "relevant", reason: "", notes: "" },
  );
  const notify = useToast();
  const save = useMutation({
    mutationFn: () =>
      post(`/opportunities/${jobId}/feedback`, { ...form, track_id: trackId }),
    onSuccess: async () => {
      await refreshWorkspace();
      notify("Feedback saved. Your preferences are unchanged.");
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const clear = useMutation({
    mutationFn: () =>
      request(`/opportunities/${jobId}/feedback?track_id=${trackId}`, {
        method: "DELETE",
      }),
    onSuccess: () => refreshWorkspace(),
    onError: (error) => notify(errorMessage(error), "error"),
  });
  return (
    <section className="feedback-section">
      <details className="workflow-disclosure">
        <summary>
          Your relevance label{initial ? `: ${initial.label}` : ""}
        </summary>
        <form
          className="workflow-form"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <fieldset className="feedback-labels">
            <legend className="sr-only">Relevance</legend>
            {(
              [
                { value: "relevant", name: "Relevant", icon: ThumbsUp },
                { value: "adjacent", name: "Adjacent", icon: CornerUpRight },
                { value: "irrelevant", name: "Not relevant", icon: ThumbsDown },
              ] as const
            ).map((choice) => (
              <label
                className={form.label === choice.value ? "selected" : ""}
                key={choice.value}
              >
                <input
                  type="radio"
                  name={`feedback-${jobId}`}
                  value={choice.value}
                  checked={form.label === choice.value}
                  onChange={() => setForm({ ...form, label: choice.value })}
                />
                <choice.icon size={15} />
                {choice.name}
              </label>
            ))}
          </fieldset>
          <Field id={`feedback-reason-${jobId}`} label="Reason" optional>
            <select
              id={`feedback-reason-${jobId}`}
              value={form.reason}
              onChange={(event) =>
                setForm({ ...form, reason: event.target.value })
              }
            >
              <option value="">No specific reason</option>
              {[
                ["good_fit", "Good fit"],
                ["wrong_role", "Wrong role"],
                ["too_senior", "Too senior"],
                ["too_junior", "Too junior"],
                ["wrong_location", "Wrong location"],
                ["salary", "Compensation"],
                ["sponsorship", "Work authorization"],
                ["not_interested", "Not interested"],
              ].map(([value, name]) => (
                <option key={value} value={value}>
                  {name}
                </option>
              ))}
            </select>
          </Field>
          <Field id={`feedback-notes-${jobId}`} label="Notes" optional>
            <textarea
              id={`feedback-notes-${jobId}`}
              rows={2}
              maxLength={2000}
              value={form.notes}
              onChange={(event) =>
                setForm({ ...form, notes: event.target.value })
              }
            />
          </Field>
          <div className="button-row">
            <button
              className="button secondary small"
              disabled={save.isPending}
            >
              {save.isPending ? <Spinner /> : <Save size={15} />}Save feedback
            </button>
            {initial && (
              <IconButton
                label="Clear relevance label"
                disabled={clear.isPending}
                onClick={() => clear.mutate()}
              >
                <Trash2 size={15} />
              </IconButton>
            )}
            {form.reason && form.reason !== "good_fit" && (
              <Link className="text-button" to="/profile">
                Review preferences
              </Link>
            )}
          </div>
        </form>
      </details>
    </section>
  );
}
