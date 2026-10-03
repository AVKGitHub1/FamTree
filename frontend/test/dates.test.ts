import { describe, expect, it } from "vitest";
import { formatPartialDate, parseFields, toFields } from "../src/lib/dates";
import { parseDraft } from "../src/lib/drafts";

describe("partial dates", () => {
  it("formats without inventing components", () => {
    expect(formatPartialDate({ year: null, month: 5, day: 12 })).toBe("12 May");
    expect(formatPartialDate({ year: 1990, month: 5, day: null })).toBe("May 1990");
    expect(formatPartialDate({ year: 1990, month: null, day: null })).toBe("1990");
  });

  it("parses a birthday without a year", () => {
    expect(parseFields({ day: "29", month: "2", year: "" })).toEqual({
      ok: true,
      value: { year: null, month: 2, day: 29 },
    });
  });

  it("treats all-empty fields as no date at all", () => {
    expect(parseFields({ day: "", month: "", year: "" })).toEqual({ ok: true, value: null });
  });

  it("rejects incomplete or impossible dates", () => {
    expect(parseFields({ day: "5", month: "", year: "1990" }).ok).toBe(false);
    expect(parseFields({ day: "", month: "4", year: "" }).ok).toBe(false);
    expect(parseFields({ day: "31", month: "4", year: "2000" }).ok).toBe(false);
    expect(parseFields({ day: "29", month: "2", year: "2001" }).ok).toBe(false);
  });

  it("round-trips through the form fields", () => {
    const date = { year: null, month: 12, day: 25 };
    expect(parseFields(toFields(date))).toEqual({ ok: true, value: date });
  });
});

describe("attribute drafts", () => {
  it("validates numbers and links", () => {
    expect(parseDraft({ type: "number", text: "4.5" })).toEqual({ ok: true, value: 4.5 });
    expect(parseDraft({ type: "number", text: "four" }).ok).toBe(false);
    expect(parseDraft({ type: "url", text: "javascript:alert(1)" }).ok).toBe(false);
    expect(parseDraft({ type: "text", text: "   " })).toEqual({ ok: true, value: null });
  });
});
