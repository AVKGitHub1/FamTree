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
  selectedId: string | null;
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
  | { type: "setWindow"; window: GenerationWindow | null }
  | { type: "closeDetails" }
  | { type: "relationStart"; first?: string }
  | { type: "relationPick"; id: string }
  | { type: "relationResult"; outcome: RelationOutcome | null; error: string | null }
  | { type: "relationActive"; index: number }
  | { type: "relationSwap" }
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
      };
    case "deselect":
      return { ...state, selectedId: null, window: null, detailsOpen: false };
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
    case "forget":
      // A person disappeared (deleted, or no longer visible after sign-out).
      return state.selectedId === action.id ? { ...state, selectedId: null, window: null, detailsOpen: false } : state;
  }
}
