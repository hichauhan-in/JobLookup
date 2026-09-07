import type { Profile } from "../types";
import { Field, TagInput } from "./ui";

export function PreferenceFields({
  profile,
  onChange,
  prefix = "eligibility",
}: {
  profile: Profile;
  onChange: (patch: Partial<Profile>) => void;
  prefix?: string;
}) {
  return (
    <>
      <div className="form-grid">
        <Field id={`${prefix}-salary`} label="Minimum pay" optional>
          <input
            id={`${prefix}-salary`}
            type="number"
            min="0"
            max="1000000000"
            value={profile.min_salary || ""}
            onChange={(event) =>
              onChange({
                min_salary: Number(event.target.value),
                salary_currency: profile.salary_currency || "INR",
                salary_period: profile.salary_period || "year",
              })
            }
          />
        </Field>
        <Field id={`${prefix}-currency`} label="Currency">
          <select
            id={`${prefix}-currency`}
            value={profile.salary_currency || "INR"}
            onChange={(event) =>
              onChange({ salary_currency: event.target.value })
            }
          >
            {["INR", "USD", "GBP", "EUR", "CAD", "AUD", "SGD", "AED"].map(
              (currency) => (
                <option key={currency}>{currency}</option>
              ),
            )}
          </select>
        </Field>
        <Field id={`${prefix}-period`} label="Pay period">
          <select
            id={`${prefix}-period`}
            value={profile.salary_period || "year"}
            onChange={(event) =>
              onChange({ salary_period: event.target.value })
            }
          >
            {["year", "month", "week", "day", "hour"].map((period) => (
              <option key={period} value={period}>
                Per {period}
              </option>
            ))}
          </select>
        </Field>
        <Field
          id={`${prefix}-timezone`}
          label="Working-hours evidence"
          optional
        >
          <input
            id={`${prefix}-timezone`}
            value={profile.timezone_requirement || ""}
            placeholder="e.g. IST, UTC+5:30"
            onChange={(event) =>
              onChange({ timezone_requirement: event.target.value })
            }
          />
        </Field>
      </div>
      <label className="workflow-check">
        <input
          type="checkbox"
          checked={profile.needs_sponsorship || false}
          onChange={(event) =>
            onChange({ needs_sponsorship: event.target.checked })
          }
        />
        Visa sponsorship required
      </label>
      <Field id={`${prefix}-countries`} label="Authorized to work in" optional>
        <TagInput
          id={`${prefix}-countries`}
          values={profile.authorized_countries || []}
          onChange={(values) => onChange({ authorized_countries: values })}
          placeholder="Add a country"
        />
      </Field>
      <Field id={`${prefix}-criteria`} label="Other posting criteria" optional>
        <TagInput
          id={`${prefix}-criteria`}
          values={profile.required_keywords || []}
          onChange={(values) => onChange({ required_keywords: values })}
          placeholder="e.g. relocation assistance"
        />
      </Field>
      <fieldset className="priority-controls">
        <legend>Preference strength</legend>
        {[
          ["location", "Location"],
          ["work_mode", "Work arrangement"],
          ["employment", "Employment type"],
          ["salary", "Compensation"],
          ["sponsorship", "Work authorization"],
          ["timezone", "Working hours"],
          ["qualifications", "Other criteria"],
        ].map(([key, name]) => (
          <label key={key} htmlFor={`${prefix}-${key}-priority`}>
            <span>{name}</span>
            <select
              id={`${prefix}-${key}-priority`}
              value={profile.constraint_modes?.[key] || "required"}
              onChange={(event) =>
                onChange({
                  constraint_modes: {
                    ...profile.constraint_modes,
                    [key]: event.target.value as
                      "required" | "preferred" | "any",
                  },
                })
              }
            >
              <option value="required">Required</option>
              <option value="preferred">Preferred</option>
              <option value="any">Any</option>
            </select>
          </label>
        ))}
      </fieldset>
    </>
  );
}
