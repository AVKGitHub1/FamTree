import { describe, expect, it } from "vitest";
import type { Point, TreeData } from "../src/api/types";
import {
  applyStep,
  canStep,
  continuations,
  isFull,
  shownBy,
  limitsFor,
  resolveWindow,
  visibleConnectors,
  visibleCrossings,
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
      { id: "f1", type: "family", people: ["gp", "p"], links: ["l1"], paths: [], dots: [], junction: null, branches: {}, bus: null, trunk: null, drops: {} },
      { id: "f2", type: "family", people: ["p", "c"], links: ["l2"], paths: [], dots: [], junction: null, branches: {}, bus: null, trunk: null, drops: {} },
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

describe("connectors shared by parents in different generations", () => {
  // P -> Q, P -> C and Q -> C: C's parents P (row 0) and Q (row 1) share one
  // junction connector, with one branch (path) per parent.
  const p: Point[] = [[0, 50], [0, 230], [50, 230], [50, 240]];
  const q: Point[] = [[100, 150], [100, 230], [50, 230], [50, 240]];
  const trunk: Point[] = [[50, 258], [50, 300]];
  const shared: TreeData = {
    people: ["P", "Q", "C", "X"].map((id) => ({ id, name: id, attributes: [] })),
    parent_links: [
      { id: "pq", parent_id: "P", child_id: "Q", role: "father" },
      { id: "pc", parent_id: "P", child_id: "C", role: "father" },
      { id: "qc", parent_id: "Q", child_id: "C", role: "mother" },
    ],
    spouse_links: [],
    definitions: [],
    layout: {
      width: 400,
      height: 400,
      rows: [0, 1, 2].map((index) => ({ index, top: index * 100, bottom: index * 100 + 50 })),
      nodes: { P: node(0), Q: node(1, 100), C: node(2), X: node(1, 300) },
      connectors: [
        { id: "f:pq", type: "family", people: ["P", "Q"], links: ["pq"], paths: [], dots: [], junction: null, branches: {}, bus: null, trunk: null, drops: {} },
        {
          id: "f:c",
          type: "family",
          people: ["P", "Q", "C"],
          links: ["pc", "qc"],
          paths: [p, q, trunk],
          dots: [],
          junction: { x: 50, y: 249, width: 58, height: 18 },
          branches: { P: 0, Q: 1 },
          bus: null,
          trunk: null,
          drops: {},
        },
        { id: "f:x", type: "family", people: ["X"], links: [], paths: [[[300, 200], [300, 260]]], dots: [], junction: null, branches: {}, bus: null, trunk: null, drops: {} },
      ],
      crossings: [
        { x: 0, y: 200, over: "f:c", under: "f:x", over_branch: "P", under_branch: null },
        { x: 100, y: 200, over: "f:c", under: "f:x", over_branch: "Q", under_branch: null },
      ],
    },
  };
  const index = buildIndex(shared);

  it("keeps the branches of included parents when another parent is hidden", () => {
    const range = visibleRange(1, { above: 0, below: 1 }, index.maxRow);
    const connectors = visibleConnectors(index, range);
    expect(connectors.map((c) => c.id)).toEqual(["f:c", "f:x"]); // P -> Q is hidden with P
    const family = connectors[0];
    expect(family.paths).toEqual([q, trunk]);
    expect(family.branches).toEqual({ Q: 0 });
    expect(family.junction).not.toBeNull();
    expect(visibleCrossings(index, connectors, range).map((x) => x.over_branch)).toEqual(["Q"]);
    expect(continuations(index, range).get("C")).toEqual({ up: true, down: false, side: false });
  });

  it("drops the connector when no parent or no child is included", () => {
    expect(visibleConnectors(index, { lo: 2, hi: 2 }).map((c) => c.id)).toEqual([]);
    expect(visibleConnectors(index, { lo: 0, hi: 1 }).map((c) => c.id)).toEqual(["f:pq", "f:x"]);
  });

  it("draws everything when every endpoint is included", () => {
    const all = visibleConnectors(index, { lo: 0, hi: 2 });
    expect(all.find((c) => c.id === "f:c")).toBe(shared.layout.connectors[1]);
    expect(visibleCrossings(index, all, { lo: 0, hi: 2 })).toHaveLength(2);
  });
});

describe("viewing only selected people", () => {
  // Mum and Dad (row 0) with children A, B, C (row 1) hanging from one bus;
  // G -> H's line crosses that bus at x = 300.
  const trunk: Point[] = [[150, 25], [150, 80]];
  const bus: Point[] = [[50, 80], [350, 80]];
  const drop = (x: number): Point[] => [[x, 80], [x, 100]];
  const kids = ["A", "B", "C"];
  const family: TreeData = {
    people: ["M", "D", ...kids, "G", "H"].map((id) => ({ id, name: id, attributes: [] })),
    parent_links: [
      ...kids.flatMap((kid) => [
        { id: `m${kid}`, parent_id: "M", child_id: kid, role: "mother" as const },
        { id: `d${kid}`, parent_id: "D", child_id: kid, role: "father" as const },
      ]),
      { id: "gh", parent_id: "G", child_id: "H", role: "father" },
    ],
    spouse_links: [{ id: "md", a: "D", b: "M" }],
    definitions: [],
    layout: {
      width: 600,
      height: 200,
      rows: [0, 1].map((index) => ({ index, top: index * 100, bottom: index * 100 + 50 })),
      nodes: { M: node(0), D: node(0, 200), A: node(1), B: node(1, 150), C: node(1, 300), G: node(0, 400), H: node(1, 450) },
      connectors: [
        { id: "s", type: "spouse", people: ["M", "D"], links: ["md"], paths: [[[100, 25], [200, 25]]], dots: [], junction: null, branches: {}, bus: null, trunk: null, drops: {} },
        {
          id: "f",
          type: "family",
          people: ["M", "D", ...kids],
          links: ["mA", "dA", "mB", "dB", "mC", "dC"],
          paths: [trunk, bus, drop(50), drop(200), drop(350)],
          dots: [[150, 80], [200, 80]],
          junction: null,
          branches: {},
          bus: 1,
          trunk: 0,
          drops: { A: 2, B: 3, C: 4 },
        },
        { id: "g", type: "family", people: ["G", "H"], links: ["gh"], paths: [[[300, 60], [300, 100]]], dots: [], junction: null, branches: {}, bus: null, trunk: null, drops: {} },
      ],
      crossings: [{ x: 300, y: 80, over: "g", under: "f", over_branch: null, under_branch: null }],
    },
  };
  const index = buildIndex(family);
  const all = { lo: 0, hi: 1 };
  const only = (...ids: string[]) => new Set([...ids, "G", "H"]);

  it("narrows the generation rows to the chosen people", () => {
    const shown = shownBy(index, { lo: 1, hi: 1 }, only("M", "A", "B"));
    expect(["M", "A", "B", "C"].filter(shown)).toEqual(["A", "B"]);
    expect(["M", "C"].filter(shownBy(index, all))).toEqual(["M", "C"]);
  });

  it("leaves out the drops of hidden children and shortens the bus", () => {
    const connectors = visibleConnectors(index, all, only("M", "D", "A", "B"));
    expect(connectors.map((c) => c.id)).toEqual(["s", "f", "g"]);
    const part = connectors[1];
    expect(part.paths).toEqual([trunk, [[50, 80], [200, 80]], drop(50), drop(200)]);
    expect(part.dots).toEqual([[150, 80]]);
    expect(part.drops).toEqual({ A: 2, B: 3 });
    expect([part.bus, part.trunk]).toEqual([1, 0]);
    expect(part.links).toEqual(["mA", "dA", "mB", "dB"]);
    // The crossing was on the part of the bus that is gone.
    expect(visibleCrossings(index, connectors, all, only("M", "D", "A", "B"))).toEqual([]);
    expect(continuations(index, all, only("M", "D", "A", "B")).get("M")).toEqual({ up: false, down: true, side: false });
    expect(continuations(index, all, only("M", "D", "A", "B")).has("A")).toBe(false);
  });

  it("keeps the bus reaching the trunk, with dots only where lines branch", () => {
    const [, part] = visibleConnectors(index, all, only("M", "D", "B"));
    expect(part.paths).toEqual([trunk, [[150, 80], [200, 80]], drop(200)]);
    expect(part.dots).toEqual([]);
  });

  it("keeps crossings where the shortened bus still runs", () => {
    const shown = only("M", "D", "A", "C");
    const connectors = visibleConnectors(index, all, shown);
    expect(connectors[1].paths[1]).toEqual(bus);
    expect(visibleCrossings(index, connectors, all, shown)).toHaveLength(1);
  });

  it("does not draw a family without a shown parent or child, nor a half couple", () => {
    expect(visibleConnectors(index, all, only("A", "B", "C")).map((c) => c.id)).toEqual(["g"]);
    expect(visibleConnectors(index, all, only("M", "D")).map((c) => c.id)).toEqual(["s", "g"]);
    expect(visibleConnectors(index, all, only("M", "A", "B")).map((c) => c.id)).toEqual(["g"]);
  });

  it("draws everything when everyone is chosen", () => {
    const connectors = visibleConnectors(index, all, only("M", "D", ...kids));
    expect(connectors).toEqual(family.layout.connectors);
    expect(connectors[1]).toBe(family.layout.connectors[1]);
    expect(visibleCrossings(index, connectors, all, only("M", "D", ...kids))).toHaveLength(1);
  });
});
