import type { AttributeValue, PartialDate, ValueType } from "../api/types";
import { parseFields, toFields, type DateFields } from "./dates";

/** Editable draft of one attribute value; converted on save. */
export type Draft = { type: "date"; fields: DateFields } | { type: Exclude<ValueType, "date">; text: string };

export function draftFrom(type: ValueType, value: AttributeValue | null): Draft {
  if (type === "date") return { type, fields: toFields((value as PartialDate | null) ?? null) };
  return { type, text: value == null ? "" : String(value) };
}

export type Parsed = { ok: true; value: AttributeValue | null } | { ok: false; error: string };

/** null value = empty (nothing to store). */
export function parseDraft(draft: Draft): Parsed {
  if (draft.type === "date") return parseFields(draft.fields);
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
