import { describe, expect, it } from "vitest";
import { resolveTheme } from "../src/state/theme";

describe("themes", () => {
  it("follows the system setting unless a theme is chosen", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("sepia", true)).toBe("sepia");
    expect(resolveTheme("light", true)).toBe("light");
  });
});
