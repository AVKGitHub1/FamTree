import { describe, expect, it } from "vitest";
import type { TreeData } from "../src/api/types";
import {
  applyStep,
  canStep,
  continuations,
  isFull,
  limitsFor,
  resolveWindow,
  visibleConnectors,
  visibleRange,
} from "../src/lib/generations";
import { buildIndex } from "../src/lib/treeIndex";

const node = (row: number, x = 0) => ({ x, y: row * 100, width: 100, height: 50, row });

// Grandparent (row 0) -> Parent (row 1) -> Child (row 2), plus a cousin on row 2.
const data: TreeData = {
  people: ["gp", "p", "c", "cousin"].map((id) => ({ id, name: id, attributes: [] })),
  parent_links: [
    { id: "l1", parent_id: "gp", child_id: "p", role: "father" },
    { id: "l2", parent_id: "p", child_id: "c", role: "mother" },
  ],
  spouse_links: [],
  definitions: [],
  layout: {
    width: 400,
    height: 300,
    rows: [0, 1, 2].map((index) => ({ index, top: index * 100, bottom: index * 100 + 50 })),
    nodes: { gp: node(0), p: node(1), c: node(2), cousin: node(2, 200) },
    connectors: [
      { id: "f1", type: "family", people: ["gp", "p"], links: ["l1"], paths: [], dots: [], junction: null },
      { id: "f2", type: "family", people: ["p", "c"], links: ["l2"], paths: [], dots: [], junction: null },
    ],
    crossings: [],
  },
};

describe("generation window", () => {
  const index = buildIndex(data);
  const limits = limitsFor(1, index.maxRow);

  it("starts with all available rows in both directions", () => {
    const window = resolveWindow(null, limits);
    expect(window).toEqual({ above: 1, below: 1 });
    expect(isFull(window, limits)).toBe(true);
  });

  it("moves one generation at a time and stops at the limits", () => {
    let window = resolveWindow(null, limits);
    expect(canStep(window, limits, "moreAbove")).toBe(false);
    window = applyStep(window, limits, "fewerAbove");
    expect(window).toEqual({ above: 0, below: 1 });
    expect(canStep(window, limits, "fewerAbove")).toBe(false);
    expect(applyStep(window, limits, "fewerAbove")).toEqual(window); // never below zero
    window = applyStep(window, limits, "fewerBelow");
    expect(window).toEqual({ above: 0, below: 0 });
    window = applyStep(window, limits, "moreBelow");
    expect(window).toEqual({ above: 0, below: 1 });
  });

  it("filters rows across the whole tree, keeping the selected row", () => {
    const range = visibleRange(1, { above: 0, below: 1 }, index.maxRow);
    expect(range).toEqual({ lo: 1, hi: 2 });
    // The cousin is on an included row even though it is not a descendant of "p".
    const ids = visibleConnectors(index, range).map((c) => c.id);
    expect(ids).toEqual(["f2"]); // f1 has a hidden endpoint, so it is not drawn
  });

  it("marks continuations only where authorized relatives are hidden", () => {
    const marks = continuations(index, { lo: 1, hi: 1 });
    expect(marks.get("p")).toEqual({ up: true, down: true, side: false });
    expect(marks.has("gp")).toBe(false);
  });
});
