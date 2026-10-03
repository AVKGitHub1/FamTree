import type { AttributeDefinition, ParentLink, Person, SpouseLink, TreeData } from "../api/types";

/** Lookups derived once per tree payload. */
export interface TreeIndex {
  data: TreeData;
  people: Map<string, Person>;
  definitions: Map<string, AttributeDefinition>;
  parentsOf: Map<string, ParentLink[]>;
  childrenOf: Map<string, ParentLink[]>;
  spousesOf: Map<string, SpouseLink[]>;
  rowOf: Map<string, number>;
  maxRow: number;
  /** Card ids per row, left to right, for keyboard navigation. */
  rows: string[][];
}

function push<K, V>(map: Map<K, V[]>, key: K, value: V) {
  const list = map.get(key);
  if (list) list.push(value);
  else map.set(key, [value]);
}

export function buildIndex(data: TreeData): TreeIndex {
  const parentsOf = new Map<string, ParentLink[]>();
  const childrenOf = new Map<string, ParentLink[]>();
  const spousesOf = new Map<string, SpouseLink[]>();
  for (const link of data.parent_links) {
    push(parentsOf, link.child_id, link);
    push(childrenOf, link.parent_id, link);
  }
  for (const link of data.spouse_links) {
    push(spousesOf, link.a, link);
    push(spousesOf, link.b, link);
  }
  const rowOf = new Map<string, number>();
  const rows: string[][] = [];
  const nodes = Object.entries(data.layout.nodes).sort(([, a], [, b]) => a.x - b.x);
  for (const [id, node] of nodes) {
    rowOf.set(id, node.row);
    (rows[node.row] ??= []).push(id);
  }
  return {
    data,
    people: new Map(data.people.map((p) => [p.id, p])),
    definitions: new Map(data.definitions.map((d) => [d.id, d])),
    parentsOf,
    childrenOf,
    spousesOf,
    rowOf,
    maxRow: Math.max(0, data.layout.rows.length - 1),
    rows: Array.from(rows, (r) => r ?? []),
  };
}

export function spouseOther(link: SpouseLink, personId: string): string {
  return link.a === personId ? link.b : link.a;
}

export function nameOf(index: TreeIndex, id: string): string {
  return index.people.get(id)?.name ?? "Unknown";
}
