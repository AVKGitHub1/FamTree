import { useId } from "react";
import { MONTHS, type DateFields } from "../../lib/dates";
import type { Draft } from "../../lib/drafts";

interface Props {
  label: string;
  draft: Draft;
  onChange: (draft: Draft) => void;
}

export function ValueInput({ label, draft, onChange }: Props) {
  const id = useId();
  if (draft.type === "date") {
    const set = (patch: Partial<DateFields>) => onChange({ ...draft, fields: { ...draft.fields, ...patch } });
    return (
      <fieldset className="date-input">
        <legend>{label}</legend>
        <input
          aria-label={`${label}: day`}
          inputMode="numeric"
          placeholder="Day"
          value={draft.fields.day}
          onChange={(e) => set({ day: e.target.value })}
        />
        <select aria-label={`${label}: month`} value={draft.fields.month} onChange={(e) => set({ month: e.target.value })}>
          <option value="">Month</option>
          {MONTHS.map((m, i) => (
            <option key={m} value={i + 1}>
              {m}
            </option>
          ))}
        </select>
        <input
          aria-label={`${label}: year (optional)`}
          inputMode="numeric"
          placeholder="Year (optional)"
          value={draft.fields.year}
          onChange={(e) => set({ year: e.target.value })}
        />
      </fieldset>
    );
  }
  const common = {
    id,
    value: draft.text,
    onChange: (e: { target: { value: string } }) => onChange({ ...draft, text: e.target.value }),
  };
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {draft.type === "long_text" ? (
        <textarea rows={3} maxLength={4000} {...common} />
      ) : (
        <input
          type={draft.type === "url" ? "url" : "text"}
          inputMode={draft.type === "number" ? "decimal" : undefined}
          maxLength={draft.type === "url" ? 2000 : 300}
          {...common}
        />
      )}
    </div>
  );
}
