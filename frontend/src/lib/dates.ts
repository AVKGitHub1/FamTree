import type { PartialDate } from "../api/types";

export const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** Mirrors the server: never invents a missing year, month or day. */
export function formatPartialDate(date: PartialDate): string {
  const { year, month, day } = date;
  if (month == null) return String(year ?? "");
  const name = MONTHS[month - 1];
  if (day == null) return `${name} ${year}`;
  if (year == null) return `${day} ${name}`;
  return `${day} ${name} ${year}`;
}

export interface DateFields {
  day: string;
  month: string; // "" or "1".."12"
  year: string;
}

export function toFields(date: PartialDate | null): DateFields {
  return {
    day: date?.day != null ? String(date.day) : "",
    month: date?.month != null ? String(date.month) : "",
    year: date?.year != null ? String(date.year) : "",
  };
}

export type ParsedDate = { ok: true; value: PartialDate | null } | { ok: false; error: string };

function daysIn(month: number, year: number | null): number {
  // Without a year, 29 February is allowed (a birthday can fall on it).
  return new Date(year ?? 2000, month, 0).getDate();
}

/** Empty fields mean "no date" (distinct from a partial date). */
export function parseFields(fields: DateFields): ParsedDate {
  const day = fields.day.trim() ? Number(fields.day) : null;
  const month = fields.month ? Number(fields.month) : null;
  const year = fields.year.trim() ? Number(fields.year) : null;
  if (day == null && month == null && year == null) return { ok: true, value: null };
  for (const [label, value] of [["Day", day], ["Year", year]] as const) {
    if (value != null && !Number.isInteger(value)) return { ok: false, error: `${label} must be a whole number.` };
  }
  if (year != null && (year < 1 || year > 9999)) return { ok: false, error: "Year must be between 1 and 9999." };
  if (day != null && month == null) return { ok: false, error: "Choose a month for this day." };
  if (month != null && year == null && day == null) {
    return { ok: false, error: "Add a day (for a birthday without a year) or a year." };
  }
  if (day != null && month != null && (day < 1 || day > daysIn(month, year))) {
    return { ok: false, error: `${MONTHS[month - 1]} has no day ${day}.` };
  }
  return { ok: true, value: { year, month, day } };
}
