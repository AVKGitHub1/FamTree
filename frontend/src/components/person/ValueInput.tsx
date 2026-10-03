import { useId, useState } from "react";
import { ApiError } from "../../api/client";
import { uploadPicture } from "../../api/endpoints";
import { MONTHS, type DateFields } from "../../lib/dates";
import type { Draft, PictureDraft } from "../../lib/drafts";
import { prepareForUpload } from "../../lib/pictures";

interface Props {
  label: string;
  draft: Draft;
  onChange: (draft: Draft) => void;
}

export function ValueInput({ label, draft, onChange }: Props) {
  const id = useId();
  if (draft.type === "image") return <PictureInput label={label} draft={draft} onChange={onChange} />;
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

/** Uploading happens on choosing the file; the person's details are saved
 * with the picture as usual. */
function PictureInput({ label, draft, onChange }: { label: string; draft: PictureDraft; onChange: (draft: Draft) => void }) {
  const inputId = useId();
  const [error, setError] = useState<string | null>(null);

  const choose = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    onChange({ ...draft, uploading: true });
    try {
      const uploaded = await uploadPicture(await prepareForUpload(file));
      onChange({ type: "image", id: uploaded.id, preview: uploaded.preview, uploading: false });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upload the picture.");
      onChange({ ...draft, uploading: false });
    }
  };

  return (
    <fieldset className="picture-input">
      <legend>{label}</legend>
      {draft.preview ? (
        <img className="avatar avatar--large" src={draft.preview} alt="" />
      ) : (
        <span className="avatar avatar--large avatar--empty" aria-hidden="true" />
      )}
      <div className="picture-input__actions">
        <label className="button" htmlFor={inputId}>
          {draft.id ? "Replace picture…" : "Choose picture…"}
        </label>
        <input
          id={inputId}
          className="sr-only"
          type="file"
          accept="image/*"
          disabled={draft.uploading}
          onChange={(event) => {
            void choose(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
        {draft.uploading && <span className="muted">Uploading…</span>}
        {error && (
          <span className="error-text" role="alert">
            {error}
          </span>
        )}
      </div>
    </fieldset>
  );
}
