import { describe, expect, it } from "vitest";
import type { ParentLink, TreeData } from "../src/api/types";
import { siblingGroup, siblingMove } from "../src/lib/siblings";
import { buildIndex } from "../src/lib/treeIndex";

const node = (row: number, x: number) => ({ x, y: row * 100, width: 100, height: 50, row });
const link = (parent: string, child: string, role: ParentLink["role"]): ParentLink => ({
  id: `${parent}>${child}`,
  parent_id: parent,
  child_id: child,
  role,
});

// Mom and Dad's children a, b, c on row 1 (drawn c, a, b) and d on row 2;
// Mom's child "half" with no recorded father sits between a and b.
const data: TreeData = {
  people: ["mom", "dad", "a", "b", "c", "d", "half"].map((id) => ({ id, name: id.toUpperCase(), attributes: [] })),
  parent_links: ["a", "b", "c", "d"].flatMap((child) => [link("mom", child, "mother"), link("dad", child, "father")]).concat(
    link("mom", "half", "mother"),
  ),
  spouse_links: [],
  definitions: [],
  layout: {
    width: 1000,
    height: 300,
    rows: [0, 1, 2].map((index) => ({ index, top: index * 100, bottom: index * 100 + 50 })),
    nodes: {
      mom: node(0, 300),
      dad: node(0, 500),
      c: node(1, 100),
      a: node(1, 300),
      half: node(1, 450),
      b: node(1, 600),
      d: node(2, 200),
    },
    connectors: [],
    crossings: [],
  },
};
const index = buildIndex(data);

describe("siblings", () => {
  it("are the children of exactly the same parents", () => {
    expect(siblingGroup(index, "a").sort()).toEqual(["a", "b", "c", "d"]);
    expect(siblingGroup(index, "half")).toEqual(["half"]);
    expect(siblingGroup(index, "mom")).toEqual([]);
  });

  it("move past the neighbour drawn beside them, listing the whole group as drawn", () => {
    // Drawn left to right: c, d (row 2), a, b.
    expect(siblingMove(index, "a", "left")).toEqual(["a", "c", "d", "b"]);
    expect(siblingMove(index, "a", "right")).toEqual(["c", "d", "b", "a"]);
    expect(siblingMove(index, "b", "left")).toEqual(["c", "d", "b", "a"]);
  });

  it("stop at the ends of their row", () => {
    expect(siblingMove(index, "c", "left")).toBeNull();
    expect(siblingMove(index, "b", "right")).toBeNull();
    expect(siblingMove(index, "d", "left")).toBeNull(); // alone on its row
    expect(siblingMove(index, "half", "right")).toBeNull();
    expect(siblingMove(index, "mom", "right")).toBeNull();
  });
});
