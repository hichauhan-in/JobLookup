import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarClock, Plus, Save, Settings2, Trash2 } from "lucide-react";
import {
  errorMessage,
  queryClient,
  refreshWorkspace,
  request,
  useTracks,
  useWorkspace,
} from "../api";
import type { SearchTrack, Sources } from "../types";
import {
  Confirm,
  Dialog,
  ErrorState,
  Field,
  IconButton,
  Spinner,
  TagInput,
} from "./ui";
import { useToast } from "./notifications";
import { PreferenceFields } from "./PreferenceFields";

export function SearchTracks({
  value,
  onChange,
}: {
  value: number;
  onChange: (id: number) => void;
}) {
  const tracks = useTracks();
  const workspace = useWorkspace();
  const [editing, setEditing] = useState<SearchTrack | "new" | null>(null);
  return (
    <div className="track-bar">
      <label htmlFor="search-track">Search track</label>
      <select
        id="search-track"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        disabled={tracks.isPending}
      >
        <option value="0">Main profile</option>
        {tracks.data?.items.map((track) => (
          <option key={track.id} value={track.id}>
            {track.name}
            {track.schedule_enabled ? " (scheduled)" : ""}
          </option>
        ))}
      </select>
      <IconButton
        label="Create search track"
        disabled={!workspace.isSuccess}
        onClick={() => setEditing("new")}
      >
        <Plus size={17} />
      </IconButton>
      {!!value && (
        <IconButton
          label="Edit search track"
          onClick={() =>
            setEditing(
              tracks.data?.items.find((track) => track.id === value) || null,
            )
          }
        >
          <Settings2 size={17} />
        </IconButton>
      )}
      {tracks.isError && (
        <ErrorState error={tracks.error} retry={() => void tracks.refetch()} />
      )}
      {editing && (
        <TrackEditor
          key={editing === "new" ? "new" : editing.id}
          initial={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={onChange}
        />
      )}
    </div>
  );
}

function TrackEditor({
  initial,
  onClose,
  onSaved,
}: {
  initial?: SearchTrack;
  onClose: () => void;
  onSaved: (id: number) => void;
}) {
  const workspace = useWorkspace();
  const defaultProfile = workspace.data?.profile.data || {};
  const [form, setForm] = useState({
    name: initial?.name || "",
    preferences: initial?.preferences || {
      target_titles: defaultProfile.target_titles || [],
      locations: defaultProfile.locations || [],
      work_modes: defaultProfile.work_modes || [],
      recency_days: defaultProfile.recency_days || 14,
      salary_currency: "INR",
      salary_period: "year",
    },
    sources: initial?.sources || [],
    cv_id: initial?.cv_id || null,
    schedule_enabled: initial?.schedule_enabled || false,
    schedule_hour: initial?.schedule_hour ?? 9,
    schedule_minute: initial?.schedule_minute || 0,
    schedule_weekdays: initial?.schedule_weekdays || [0, 1, 2, 3, 4],
  });
  const [remove, setRemove] = useState(false);
  const notify = useToast();
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: ({ signal }) => request<Sources>("/sources", { signal }),
  });
  const save = useMutation({
    mutationFn: () =>
      request<SearchTrack>(initial ? `/tracks/${initial.id}` : "/tracks", {
        method: initial ? "PUT" : "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: async (track) => {
      await queryClient.invalidateQueries({ queryKey: ["tracks"] });
      await refreshWorkspace();
      onSaved(track.id);
      onClose();
      notify("Search track saved.");
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  return (
    <Dialog
      title={initial ? "Edit search track" : "New search track"}
      onClose={onClose}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <div className="dialog-body workflow-form">
          <Field id="track-name" label="Track name">
            <input
              id="track-name"
              required
              maxLength={80}
              value={form.name}
              onChange={(event) =>
                setForm({ ...form, name: event.target.value })
              }
              autoFocus
            />
          </Field>
          <Field id="track-roles" label="Target roles">
            <TagInput
              id="track-roles"
              values={form.preferences.target_titles || []}
              onChange={(target_titles) =>
                setForm({
                  ...form,
                  preferences: { ...form.preferences, target_titles },
                })
              }
              placeholder="Add a target role"
            />
          </Field>
          <Field id="track-locations" label="Locations">
            <TagInput
              id="track-locations"
              values={form.preferences.locations || []}
              onChange={(locations) =>
                setForm({
                  ...form,
                  preferences: { ...form.preferences, locations },
                })
              }
              placeholder="Add a location"
            />
          </Field>
          <div className="form-grid">
            <Field id="track-cv" label="Resume focus">
              <select
                id="track-cv"
                value={form.cv_id || ""}
                onChange={(event) =>
                  setForm({
                    ...form,
                    cv_id: Number(event.target.value) || null,
                  })
                }
              >
                <option value="">Merged career profile</option>
                {workspace.data?.cvs.map((cv) => (
                  <option key={cv.id} value={cv.id}>
                    {cv.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field id="track-age" label="Posting age">
              <select
                id="track-age"
                value={form.preferences.recency_days || 14}
                onChange={(event) =>
                  setForm({
                    ...form,
                    preferences: {
                      ...form.preferences,
                      recency_days: Number(event.target.value),
                    },
                  })
                }
              >
                {[7, 14, 30, 90, 365].map((days) => (
                  <option key={days} value={days}>
                    Last {days} days
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <fieldset className="workflow-options">
            <legend>Work arrangement</legend>
            {["remote", "hybrid", "onsite"].map((mode) => (
              <label className="workflow-check" key={mode}>
                <input
                  type="checkbox"
                  checked={form.preferences.work_modes?.includes(mode) || false}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      preferences: {
                        ...form.preferences,
                        work_modes: event.target.checked
                          ? [...(form.preferences.work_modes || []), mode]
                          : form.preferences.work_modes?.filter(
                              (item) => item !== mode,
                            ),
                      },
                    })
                  }
                />
                {mode === "onsite"
                  ? "On site"
                  : mode === "hybrid"
                    ? "Hybrid"
                    : "Remote"}
              </label>
            ))}
          </fieldset>
          <details className="workflow-disclosure">
            <summary>Eligibility preferences</summary>
            <PreferenceFields
              profile={form.preferences}
              prefix="track"
              onChange={(patch) =>
                setForm({
                  ...form,
                  preferences: { ...form.preferences, ...patch },
                })
              }
            />
          </details>
          <details className="workflow-disclosure">
            <summary>Sources ({form.sources.length || "all enabled"})</summary>
            <div className="source-checklist">
              {sources.data?.sources
                .filter(
                  (source) =>
                    source.enabled || form.sources.includes(source.key),
                )
                .map((source) => (
                  <label className="workflow-check" key={source.key}>
                    <input
                      type="checkbox"
                      checked={form.sources.includes(source.key)}
                      onChange={(event) =>
                        setForm({
                          ...form,
                          sources: event.target.checked
                            ? [...form.sources, source.key]
                            : form.sources.filter((key) => key !== source.key),
                        })
                      }
                    />
                    {source.name}
                    {!source.ready && (
                      <span className="muted">Unavailable</span>
                    )}
                  </label>
                ))}
            </div>
            {sources.isError && <ErrorState error={sources.error} />}
          </details>
          <div className="section-title">
            <h3>
              <CalendarClock size={17} /> Schedule
            </h3>
            <label className="workflow-check">
              <input
                type="checkbox"
                checked={form.schedule_enabled}
                onChange={(event) =>
                  setForm({ ...form, schedule_enabled: event.target.checked })
                }
              />
              Enabled
            </label>
          </div>
          {form.schedule_enabled && (
            <div className="workflow-form">
              <Field id="track-time" label="Computer-local time">
                <input
                  id="track-time"
                  type="time"
                  required
                  value={`${String(form.schedule_hour).padStart(2, "0")}:${String(form.schedule_minute).padStart(2, "0")}`}
                  onChange={(event) => {
                    const [hour, minute] = event.target.value
                      .split(":")
                      .map(Number);
                    setForm({
                      ...form,
                      schedule_hour: hour,
                      schedule_minute: minute,
                    });
                  }}
                />
              </Field>
              <fieldset className="weekday-picker">
                <legend>Scheduled days</legend>
                {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(
                  (day, index) => (
                    <label key={day}>
                      <input
                        type="checkbox"
                        checked={form.schedule_weekdays.includes(index)}
                        onChange={(event) =>
                          setForm({
                            ...form,
                            schedule_weekdays: event.target.checked
                              ? [...form.schedule_weekdays, index]
                              : form.schedule_weekdays.filter(
                                  (value) => value !== index,
                                ),
                          })
                        }
                      />
                      {day}
                    </label>
                  ),
                )}
              </fieldset>
              <p className="muted">
                Requires JobLookup to be running. A missed time runs once later
                that same day. No days selected means every day.
              </p>
            </div>
          )}
          {save.isError && <ErrorState error={save.error} />}
        </div>
        <footer className="dialog-footer">
          {initial && (
            <IconButton
              label="Delete search track"
              onClick={() => setRemove(true)}
            >
              <Trash2 size={17} />
            </IconButton>
          )}
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="button primary"
            disabled={
              save.isPending ||
              !form.name.trim() ||
              !form.preferences.target_titles?.length
            }
          >
            {save.isPending ? <Spinner /> : <Save size={16} />}Save track
          </button>
        </footer>
      </form>
      {remove && (
        <Confirm
          title="Delete this search track?"
          detail="Jobs, applications and your labeled relevance evidence will remain. This track's schedule and inbox state will be removed."
          action="Delete track"
          onClose={() => setRemove(false)}
          onConfirm={async () => {
            await request(`/tracks/${initial!.id}`, { method: "DELETE" });
            await queryClient.invalidateQueries({ queryKey: ["tracks"] });
            onSaved(0);
            onClose();
          }}
        />
      )}
    </Dialog>
  );
}
