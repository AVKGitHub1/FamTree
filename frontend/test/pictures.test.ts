import { describe, expect, it } from "vitest";
import type { AttributeDefinition, Person } from "../src/api/types";
import { CUSTOM_VALUE_TYPES, profilePicture, PROFILE_PIC } from "../src/lib/attributes";
import { rowsFromPerson, rowsToPayload } from "../src/lib/attributeRows";
import { draftFrom, parseDraft } from "../src/lib/drafts";

const profilePic: AttributeDefinition = { id: PROFILE_PIC, label: "Profile Pic", value_type: "image", builtin: true };
const definitions = new Map([[PROFILE_PIC, profilePic]]);
const person: Person = {
  id: "p1",
  name: "Ada",
  attributes: [{ definition_id: PROFILE_PIC, value: { id: "0123456789abcdef" }, is_public: false }],
};

describe("profile pictures", () => {
  it("are not offered as a type for custom details", () => {
    expect(CUSTOM_VALUE_TYPES.map(([type]) => type)).not.toContain("image");
    expect(CUSTOM_VALUE_TYPES.map(([type]) => type)).toContain("text");
  });

  it("are found only when the caller received the picture", () => {
    expect(profilePicture(person, definitions)).toEqual({ id: "0123456789abcdef" });
    expect(profilePicture({ ...person, attributes: [] }, definitions)).toBeNull();
    expect(profilePicture(person, new Map())).toBeNull();
  });

  it("keep a stored picture when the details are saved again", () => {
    const rows = rowsFromPerson(person, definitions);
    expect(rows[0].draft).toMatchObject({ type: "image", id: "0123456789abcdef", uploading: false });
    expect((rows[0].draft as { preview: string }).preview).toBe(
      "/api/people/p1/picture?size=thumb&v=0123456789abcdef",
    );
    expect(rowsToPayload(rows, definitions).attributes).toEqual([
      { definition: { id: PROFILE_PIC }, value: { id: "0123456789abcdef" }, is_public: false },
    ]);
  });

  it("cannot be saved while still uploading, and are dropped when empty", () => {
    expect(parseDraft({ type: "image", id: null, preview: null, uploading: true })).toEqual({
      ok: false,
      error: "Wait until the picture has finished uploading.",
    });
    expect(parseDraft(draftFrom("image", null))).toEqual({ ok: true, value: null });
  });
});
