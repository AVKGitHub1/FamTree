import { describe, expect, it } from "vitest";
import type { TreeData } from "../src/api/types";
import { nameKey, namesakes } from "../src/lib/namesakes";
import { buildIndex } from "../src/lib/treeIndex";

const node = (row: number, x = 0) => ({ x, y: row * 100, width: 100, height: 50, row });
const data: TreeData = {
  people: [
    { id: "p", name: "Ana Lopez", attributes: [] },
    { id: "a", name: "José  García", attributes: [{ definition_id: "birth_date", value: { year: 1950, month: null, day: null } }] },
    { id: "b", name: "Jose Garcia", attributes: [] },
  ],
  parent_links: [{ id: "l", parent_id: "p", child_id: "b", role: "mother" }],
  spouse_links: [],
  definitions: [{ id: "birth_date", label: "Birth date", value_type: "date", builtin: true }],
  layout: {
    width: 300,
    height: 200,
    rows: [0, 1].map((index) => ({ index, top: index * 100, bottom: index * 100 + 50 })),
    nodes: { p: node(0), a: node(1), b: node(1, 150) },
    connectors: [],
    crossings: [],
  },
};
const index = buildIndex(data);

describe("namesakes", () => {
  it("compares names regardless of case, accents and spacing", () => {
    expect(nameKey("  José   GARCÍA ")).toBe("jose garcia");
    expect(nameKey("")).toBe("");
  });

  it("finds everyone of that name, with facts that tell them apart", () => {
    const found = namesakes(index, "jose garcia");
    expect(found.map((n) => n.person.id)).toEqual(["a", "b"]);
    expect(found[0].context).toEqual(["b. 1950"]);
    expect(found[1].context).toEqual(["child of Ana Lopez"]);
  });

  it("leaves out the person being renamed, and blank or unmatched names", () => {
    expect(namesakes(index, "José García", ["a"]).map((n) => n.person.id)).toEqual(["b"]);
    expect(namesakes(index, "   ")).toEqual([]);
    expect(namesakes(index, "Jose Garcias")).toEqual([]);
  });
});
