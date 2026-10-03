import type { RelationOutcome } from "../api/types";
import type { GenerationWindow } from "../lib/generations";

export type DialogState =
  | { kind: "signin" }
  | { kind: "add"; anchorId: string | null }
  | { kind: "export" }
  | { kind: "admin" }
  | { kind: "attributes" }
  | { kind: "delete"; personId: string }
  | null;

export type RelationState =
  | { stage: "idle" }
  | { stage: "pick"; first: string | null }
  | {
      stage: "result";
      first: string;
      second: string;
      outcome: RelationOutcome | null;
      error: string | null;
      active: number;
    };

export interface UiState {
  /** The person in focus: shown in the details panel, reference for the generation window. */
  selectedId: string | null;
  /** People chosen by clicking, dragging over the tree or Ctrl+clicking. */
  selection: ReadonlySet<string>;
  /** The people View Only Selected shows; null shows everyone (the default view). */
  viewOnly: ReadonlySet<string> | null;
  /** null = all available generations around the selection. */
  window: GenerationWindow | null;
  detailsOpen: boolean;
  relation: RelationState;
  dialog: DialogState;
  legendOpen: boolean;
  fitRequest: number;
}

export const initialUi: UiState = {
  selectedId: null,
  selection: new Set(),
  viewOnly: null,
  window: null,
  detailsOpen: false,
  relation: { stage: "idle" },
  dialog: null,
  legendOpen: false,
  fitRequest: 0,
};

export type UiAction =
  | { type: "select"; id: string; openDetails?: boolean }
  | { type: "deselect" }
  | { type: "setSelection"; ids: Iterable<string> }
  | { type: "toggleSelected"; id: string }
  | { type: "viewSelected" }
  | { type: "viewDefault" }
  | { type: "setWindow"; window: GenerationWindow | null }
  | { type: "closeDetails" }
  | { type: "relationStart"; first?: string }
  | { type: "relationPick"; id: string }
  | { type: "relationResult"; outcome: RelationOutcome | null; error: string | null }
  | { type: "relationActive"; index: number }
  | { type: "relationSwap" }
  | { type: "relationRecalculate" }
  | { type: "relationCancel" }
  | { type: "openDialog"; dialog: Exclude<DialogState, null> }
  | { type: "closeDialog" }
  | { type: "toggleLegend" }
  | { type: "fit" }
  | { type: "forget"; id: string };

export function uiReducer(state: UiState, action: UiAction): UiState {
  switch (action.type) {
    case "select":
      return {
        ...state,
        selectedId: action.id,
        // A new reference person starts from the full tree again.
        window: action.id === state.selectedId ? state.window : null,
        detailsOpen: action.openDetails ?? state.detailsOpen,
        // Someone chosen from the details panel or just added joins a
        // narrowed view rather than being selected out of sight.
        viewOnly: state.viewOnly && !state.viewOnly.has(action.id) ? new Set([...state.viewOnly, action.id]) : state.viewOnly,
      };
    case "deselect":
      return { ...state, selectedId: null, window: null, detailsOpen: false, selection: new Set() };
    case "setSelection":
      return { ...state, selection: new Set(action.ids) };
    case "toggleSelected": {
      const selection = new Set(state.selection);
      if (!selection.delete(action.id)) selection.add(action.id);
      return { ...state, selection };
    }
    case "viewSelected": {
      if (!state.selection.size) return state;
      const next = { ...state, viewOnly: new Set(state.selection), fitRequest: state.fitRequest + 1 };
      // The person in focus stays visible, or is let go.
      return state.selectedId && !state.selection.has(state.selectedId)
        ? { ...next, selectedId: null, window: null, detailsOpen: false }
        : next;
    }
    case "viewDefault":
      return { ...state, viewOnly: null, window: null, fitRequest: state.fitRequest + 1 };
    case "setWindow":
      return { ...state, window: action.window };
    case "closeDetails":
      return { ...state, detailsOpen: false };
    case "relationStart":
      return { ...state, relation: { stage: "pick", first: action.first ?? null }, detailsOpen: false };
    case "relationPick": {
      if (state.relation.stage !== "pick") return state;
      if (!state.relation.first) return { ...state, relation: { stage: "pick", first: action.id } };
      return {
        ...state,
        relation: { stage: "result", first: state.relation.first, second: action.id, outcome: null, error: null, active: 0 },
      };
    }
    case "relationResult":
      if (state.relation.stage !== "result") return state;
      return { ...state, relation: { ...state.relation, outcome: action.outcome, error: action.error, active: 0 } };
    case "relationActive":
      if (state.relation.stage !== "result") return state;
      return { ...state, relation: { ...state.relation, active: action.index } };
    case "relationSwap":
      if (state.relation.stage !== "result") return state;
      return {
        ...state,
        relation: { ...state.relation, first: state.relation.second, second: state.relation.first, outcome: null, error: null, active: 0 },
      };
    case "relationRecalculate":
      // Clearing the outcome makes the shell request it again.
      if (state.relation.stage !== "result") return state;
      return { ...state, relation: { ...state.relation, outcome: null, error: null } };
    case "relationCancel":
      return { ...state, relation: { stage: "idle" } };
    case "openDialog":
      return { ...state, dialog: action.dialog };
    case "closeDialog":
      return { ...state, dialog: null };
    case "toggleLegend":
      return { ...state, legendOpen: !state.legendOpen };
    case "fit":
      return { ...state, fitRequest: state.fitRequest + 1 };
    case "forget": {
      // A person disappeared (deleted, or no longer visible after sign-out).
      let next = state;
      if (state.selectedId === action.id) next = { ...next, selectedId: null, window: null, detailsOpen: false };
      if (state.selection.has(action.id)) next = { ...next, selection: without(state.selection, action.id) };
      if (state.viewOnly?.has(action.id)) {
        const viewOnly = without(state.viewOnly, action.id);
        next = { ...next, viewOnly: viewOnly.size ? viewOnly : null };
      }
      return next;
    }
  }
}

function without(set: ReadonlySet<string>, id: string): Set<string> {
  const copy = new Set(set);
  copy.delete(id);
  return copy;
}
