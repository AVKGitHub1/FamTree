// Generation filtering. For a selected person on row g, rows g-A .. g+D are
// shown, across the whole tree (not just that person's own branch).

import type { Connector } from "../api/types";
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

/** Complete connectors only: every endpoint must be visible. */
export function visibleConnectors(index: TreeIndex, range: RowRange): Connector[] {
  return index.data.layout.connectors.filter((c) =>
    c.people.every((id) => inRange(index.rowOf.get(id), range)),
  );
}

export interface Continuations {
  up: boolean; // has parents in hidden rows
  down: boolean; // has children in hidden rows
  side: boolean; // has a spouse in hidden rows
}

/** Marks for visible people whose (authorized) relatives are filtered out. */
export function continuations(index: TreeIndex, range: RowRange): Map<string, Continuations> {
  const result = new Map<string, Continuations>();
  const hidden = (id: string) => !inRange(index.rowOf.get(id), range);
  for (const [id, row] of index.rowOf) {
    if (!inRange(row, range)) continue;
    const marks = {
      up: (index.parentsOf.get(id) ?? []).some((l) => hidden(l.parent_id)),
      down: (index.childrenOf.get(id) ?? []).some((l) => hidden(l.child_id)),
      side: (index.spousesOf.get(id) ?? []).some((l) => hidden(spouseOther(l, id))),
    };
    if (marks.up || marks.down || marks.side) result.set(id, marks);
  }
  return result;
}
