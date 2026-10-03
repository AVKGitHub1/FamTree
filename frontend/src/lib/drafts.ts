import type { AttributeValue, ImageValue, PartialDate, ValueType } from "../api/types";
import { parseFields, toFields, type DateFields } from "./dates";

/** A picture being edited: the stored one, or a new upload (with its preview). */
export interface PictureDraft {
  type: "image";
  id: string | null;
  preview: string | null;
  uploading: boolean;
}

/** Editable draft of one attribute value; converted on save. */
export type Draft =
  | { type: "date"; fields: DateFields }
  | PictureDraft
  | { type: Exclude<ValueType, "date" | "image">; text: string };

/** `preview`: where to show an existing picture from. */
export function draftFrom(type: ValueType, value: AttributeValue | null, preview: string | null = null): Draft {
  if (type === "date") return { type, fields: toFields((value as PartialDate | null) ?? null) };
  if (type === "image") return { type, id: (value as ImageValue | null)?.id ?? null, preview, uploading: false };
  return { type, text: value == null ? "" : String(value) };
}

export type Parsed = { ok: true; value: AttributeValue | null } | { ok: false; error: string };

/** null value = empty (nothing to store). */
export function parseDraft(draft: Draft): Parsed {
  if (draft.type === "date") return parseFields(draft.fields);
  if (draft.type === "image") {
    if (draft.uploading) return { ok: false, error: "Wait until the picture has finished uploading." };
    return { ok: true, value: draft.id ? { id: draft.id } : null };
  }
  const text = draft.text.trim();
  if (!text) return { ok: true, value: null };
  if (draft.type === "number") {
    const n = Number(text);
    return Number.isFinite(n) ? { ok: true, value: n } : { ok: false, error: "Enter a number." };
  }
  if (draft.type === "url" && !/^https?:\/\//i.test(text)) {
    return { ok: false, error: "Links must start with http:// or https://." };
  }
  return { ok: true, value: draft.type === "long_text" ? draft.text.trim() : text };
}
