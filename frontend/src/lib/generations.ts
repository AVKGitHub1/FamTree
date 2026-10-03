// Generation filtering. For a selected person on row g, rows g-A .. g+D are
// shown, across the whole tree (not just that person's own branch). View Only
// Selected narrows that to a chosen set of people.

import type { Connector, Crossing, Point } from "../api/types";
import type { TreeIndex } from "./treeIndex";
import { spouseOther } from "./treeIndex";

/** null means "all available rows" in both directions. */
export interface GenerationWindow {
  above: number;
  below: number;
}

export interface Limits {
  maxAbove: number;
  maxBelow: number;
}

export function limitsFor(selectedRow: number, maxRow: number): Limits {
  return { maxAbove: selectedRow, maxBelow: Math.max(0, maxRow - selectedRow) };
}

export function resolveWindow(window: GenerationWindow | null, limits: Limits): GenerationWindow {
  if (!window) return { above: limits.maxAbove, below: limits.maxBelow };
  return {
    above: Math.min(Math.max(window.above, 0), limits.maxAbove),
    below: Math.min(Math.max(window.below, 0), limits.maxBelow),
  };
}

export type Step = "moreAbove" | "fewerAbove" | "moreBelow" | "fewerBelow";

export function canStep(window: GenerationWindow, limits: Limits, step: Step): boolean {
  switch (step) {
    case "moreAbove":
      return window.above < limits.maxAbove;
    case "fewerAbove":
      return window.above > 0;
    case "moreBelow":
      return window.below < limits.maxBelow;
    case "fewerBelow":
      return window.below > 0;
  }
}

export function applyStep(window: GenerationWindow, limits: Limits, step: Step): GenerationWindow {
  if (!canStep(window, limits, step)) return window;
  const delta = step === "moreAbove" || step === "moreBelow" ? 1 : -1;
  return step === "moreAbove" || step === "fewerAbove"
    ? { ...window, above: window.above + delta }
    : { ...window, below: window.below + delta };
}

export function isFull(window: GenerationWindow, limits: Limits): boolean {
  return window.above === limits.maxAbove && window.below === limits.maxBelow;
}

export interface RowRange {
  lo: number;
  hi: number;
}

export function visibleRange(selectedRow: number | null, window: GenerationWindow, maxRow: number): RowRange {
  if (selectedRow == null) return { lo: 0, hi: maxRow };
  return { lo: selectedRow - window.above, hi: selectedRow + window.below };
}

export const inRange = (row: number | undefined, range: RowRange) =>
  row != null && row >= range.lo && row <= range.hi;

/** Who is drawn: everyone on the included rows, narrowed to `only` when set. */
export function shownBy(index: TreeIndex, range: RowRange, only: ReadonlySet<string> | null = null) {
  return (id: string) => inRange(index.rowOf.get(id), range) && (!only || only.has(id));
}

/** What to draw of each connector. A connector is drawn whole when all of its
 * people are shown. A family with at least one shown parent and one shown
 * child is drawn in part when the people it misses are junction parents
 * (their branches are left out) or children (their drops are left out and the
 * bus spans only the children left). Otherwise it is not drawn (continuation
 * marks show that relatives are hidden). Exports follow the same rule on the
 * server (`Connector.visible_part`). */
export function visibleConnectors(index: TreeIndex, range: RowRange, only: ReadonlySet<string> | null = null): Connector[] {
  const shown = shownBy(index, range, only);
  const result: Connector[] = [];
  for (const c of index.data.layout.connectors) {
    const hidden = c.people.filter((id) => !shown(id));
    const part = hidden.length ? partOf(index, c, hidden) : c;
    if (part) result.push(part);
  }
  return result;
}

const EPS = 0.5; // as on the server: a dot marks a branch strictly inside its bus

function partOf(index: TreeIndex, c: Connector, hidden: string[]): Connector | null {
  const parents = hidden.filter((id) => Object.hasOwn(c.branches, id));
  const children = hidden.filter((id) => Object.hasOwn(c.drops, id));
  if (parents.length + children.length < hidden.length) return null; // a spouse, or a parent without its own branch
  if (parents.length && parents.length === Object.keys(c.branches).length) return null;
  if (children.length && children.length === Object.keys(c.drops).length) return null;

  const paths = [...c.paths];
  let dots = c.dots;
  if (children.length) {
    if (c.bus == null || c.trunk == null) return null;
    const y = paths[c.bus][0][1];
    const xs = [
      paths[c.trunk].at(-1)![0],
      ...Object.entries(c.drops)
        .filter(([id]) => !children.includes(id))
        .map(([, i]) => paths[i][0][0]),
    ];
    const lo = Math.min(...xs);
    const hi = Math.max(...xs);
    paths[c.bus] = [[lo, y], [hi, y]];
    dots = [...new Set(xs)]
      .filter((x) => lo + EPS < x && x < hi - EPS)
      .sort((a, b) => a - b)
      .map((x): Point => [x, y]);
  }

  const dropped = new Set([...parents.map((id) => c.branches[id]), ...children.map((id) => c.drops[id])]);
  const kept = paths.map((_, i) => i).filter((i) => !dropped.has(i));
  const remap = (indices: Record<string, number>) =>
    Object.fromEntries(
      Object.entries(indices)
        .filter(([, i]) => !dropped.has(i))
        .map(([id, i]) => [id, kept.indexOf(i)]),
    );
  const gone = new Set(
    hidden.flatMap((id) => [...(index.parentsOf.get(id) ?? []), ...(index.childrenOf.get(id) ?? [])].map((l) => l.id)),
  );
  return {
    ...c,
    links: c.links.filter((id) => !gone.has(id)),
    paths: kept.map((i) => paths[i]),
    dots,
    branches: remap(c.branches),
    drops: remap(c.drops),
    bus: c.bus == null ? null : kept.indexOf(c.bus),
    trunk: c.trunk == null ? null : kept.indexOf(c.trunk),
  };
}

/** Line breaks between drawn connectors, leaving out those on a hidden branch
 * and those where a connector drawn in part no longer has a line. */
export function visibleCrossings(
  index: TreeIndex,
  connectors: Connector[],
  range: RowRange,
  only: ReadonlySet<string> | null = null,
): Crossing[] {
  const shown = shownBy(index, range, only);
  const whole = new Set(index.data.layout.connectors);
  const drawn = new Map(connectors.map((c) => [c.id, c]));
  const onLine = (id: string, x: Crossing) => {
    const c = drawn.get(id);
    return c != null && (whole.has(c) || onPaths(c.paths, x.x, x.y));
  };
  const onBranch = (branch: string | null) => branch == null || shown(branch);
  return index.data.layout.crossings.filter(
    (x) => onLine(x.over, x) && onLine(x.under, x) && onBranch(x.over_branch) && onBranch(x.under_branch),
  );
}

/** Whether (x, y) lies on one of the (orthogonal) paths. */
function onPaths(paths: Point[][], x: number, y: number): boolean {
  const within = (v: number, a: number, b: number) => v >= Math.min(a, b) - 0.01 && v <= Math.max(a, b) + 0.01;
  return paths.some((path) =>
    path.some((p, i) => i > 0 && within(x, path[i - 1][0], p[0]) && within(y, path[i - 1][1], p[1])),
  );
}

export interface Continuations {
  up: boolean; // has parents who are not shown
  down: boolean; // has children who are not shown
  side: boolean; // has a spouse who is not shown
}

/** Marks for visible people whose (authorized) relatives are filtered out. */
export function continuations(
  index: TreeIndex,
  range: RowRange,
  only: ReadonlySet<string> | null = null,
): Map<string, Continuations> {
  const result = new Map<string, Continuations>();
  const shown = shownBy(index, range, only);
  const hidden = (id: string) => !shown(id);
  for (const id of index.rowOf.keys()) {
    if (hidden(id)) continue;
    const marks = {
      up: (index.parentsOf.get(id) ?? []).some((l) => hidden(l.parent_id)),
      down: (index.childrenOf.get(id) ?? []).some((l) => hidden(l.child_id)),
      side: (index.spousesOf.get(id) ?? []).some((l) => hidden(spouseOther(l, id))),
    };
    if (marks.up || marks.down || marks.side) result.set(id, marks);
  }
  return result;
}
