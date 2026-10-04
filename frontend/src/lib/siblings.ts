import type { TreeIndex } from "./treeIndex";

export type Direction = "left" | "right";

function parentKey(index: TreeIndex, id: string): string {
  return [...new Set((index.parentsOf.get(id) ?? []).map((link) => link.parent_id))].sort().join(" ");
}

/** Everyone with exactly `id`'s parents, `id` included; [] for someone without
 * parents. The server puts in order only such a group, and only whole. */
export function siblingGroup(index: TreeIndex, id: string): string[] {
  const key = parentKey(index, id);
  if (!key) return [];
  const group = new Set<string>();
  for (const link of index.parentsOf.get(id) ?? []) {
    for (const child of index.childrenOf.get(link.parent_id) ?? []) {
      if (parentKey(index, child.child_id) === key) group.add(child.child_id);
    }
  }
  return [...group];
}

/** The order to save to move `id` one place left or right among the siblings
 * drawn in its row, or null if none is drawn on that side. It lists the whole
 * group left to right as drawn, with `id` moved past that neighbour. */
export function siblingMove(index: TreeIndex, id: string, direction: Direction): string[] | null {
  const nodes = index.data.layout.nodes;
  const node = nodes[id];
  if (!node) return null;
  const drawn = siblingGroup(index, id)
    .filter((c) => nodes[c])
    .sort((a, b) => nodes[a].x - nodes[b].x || nodes[a].row - nodes[b].row);
  const row = drawn.filter((c) => nodes[c].row === node.row);
  const at = row.indexOf(id);
  const neighbour = row[direction === "left" ? at - 1 : at + 1];
  if (!neighbour) return null;
  const order = drawn.filter((c) => c !== id);
  order.splice(order.indexOf(neighbour) + (direction === "left" ? 0 : 1), 0, id);
  return order;
}
