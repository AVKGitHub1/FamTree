import { describe, expect, it } from "vitest";
import { initialUi, uiReducer, type UiState } from "../src/state/ui";
import { boxBetween, fitTransform, overlaps, panIntoView, toTree, zoomAt } from "../src/lib/viewport";

describe("ui reducer", () => {
  it("resets generation limits when a different person is selected", () => {
    let state: UiState = uiReducer(initialUi, { type: "select", id: "a" });
    state = uiReducer(state, { type: "setWindow", window: { above: 0, below: 1 } });
    expect(uiReducer(state, { type: "select", id: "a" }).window).toEqual({ above: 0, below: 1 });
    expect(uiReducer(state, { type: "select", id: "b" }).window).toBeNull();
  });

  it("runs the two-person relation selection with cancellation", () => {
    let state = uiReducer(initialUi, { type: "relationStart" });
    expect(state.relation).toEqual({ stage: "pick", first: null });
    state = uiReducer(state, { type: "relationPick", id: "a" });
    expect(state.relation).toEqual({ stage: "pick", first: "a" });
    state = uiReducer(state, { type: "relationPick", id: "b" });
    expect(state.relation).toMatchObject({ stage: "result", first: "a", second: "b" });
    state = uiReducer(state, { type: "relationSwap" });
    expect(state.relation).toMatchObject({ first: "b", second: "a" });
    expect(uiReducer(state, { type: "relationCancel" }).relation).toEqual({ stage: "idle" });
  });

  it("clears a relation result for recalculation, and ignores that when idle", () => {
    let state = uiReducer(initialUi, { type: "relationStart", first: "a" });
    state = uiReducer(state, { type: "relationPick", id: "b" });
    state = uiReducer(state, { type: "relationResult", outcome: null, error: "Could not calculate the relation." });
    expect(uiReducer(state, { type: "relationRecalculate" }).relation).toEqual({
      stage: "result",
      first: "a",
      second: "b",
      outcome: null,
      error: null,
      active: 0,
    });
    expect(uiReducer(initialUi, { type: "relationRecalculate" })).toBe(initialUi);
  });

  it("starts from the card shortcut with the first person chosen", () => {
    const state = uiReducer(initialUi, { type: "relationStart", first: "x" });
    expect(state.relation).toEqual({ stage: "pick", first: "x" });
  });
});

describe("selection and View Only Selected", () => {
  const selected = (state: UiState) => [...state.selection].sort();

  it("replaces, toggles and clears the selection", () => {
    let state = uiReducer(initialUi, { type: "setSelection", ids: ["a", "b"] });
    expect(selected(state)).toEqual(["a", "b"]);
    state = uiReducer(state, { type: "toggleSelected", id: "c" });
    state = uiReducer(state, { type: "toggleSelected", id: "a" });
    expect(selected(state)).toEqual(["b", "c"]);
    expect(uiReducer(state, { type: "deselect" }).selection.size).toBe(0);
  });

  it("shows a snapshot of the selection until the default view", () => {
    let state = uiReducer(initialUi, { type: "select", id: "a" });
    state = uiReducer(state, { type: "setWindow", window: { above: 0, below: 1 } });
    state = uiReducer(state, { type: "setSelection", ids: ["a", "b"] });
    state = uiReducer(state, { type: "viewSelected" });
    expect([...state.viewOnly!].sort()).toEqual(["a", "b"]);
    expect(state.fitRequest).toBe(1);
    expect(state.selectedId).toBe("a");
    // Changing the selection afterwards does not change what is shown.
    state = uiReducer(state, { type: "setSelection", ids: ["b"] });
    expect(state.viewOnly!.size).toBe(2);
    state = uiReducer(state, { type: "viewDefault" });
    expect(state).toMatchObject({ viewOnly: null, window: null, selectedId: "a", fitRequest: 2 });
    expect(selected(state)).toEqual(["b"]);
  });

  it("lets go of the person in focus when they are not among those shown", () => {
    let state = uiReducer(initialUi, { type: "select", id: "a", openDetails: true });
    state = uiReducer(state, { type: "setSelection", ids: ["b"] });
    state = uiReducer(state, { type: "viewSelected" });
    expect(state).toMatchObject({ selectedId: null, detailsOpen: false, window: null });
    expect(uiReducer(initialUi, { type: "viewSelected" })).toBe(initialUi); // nothing selected
  });

  it("adds a person chosen elsewhere to the narrowed view", () => {
    let state = uiReducer(initialUi, { type: "setSelection", ids: ["a"] });
    state = uiReducer(state, { type: "viewSelected" });
    state = uiReducer(state, { type: "select", id: "z", openDetails: true });
    expect([...state.viewOnly!].sort()).toEqual(["a", "z"]);
  });

  it("forgets people who disappear, falling back to the default view", () => {
    let state = uiReducer(initialUi, { type: "setSelection", ids: ["a", "b"] });
    state = uiReducer(state, { type: "viewSelected" });
    state = uiReducer(state, { type: "forget", id: "a" });
    expect(selected(state)).toEqual(["b"]);
    expect([...state.viewOnly!]).toEqual(["b"]);
    state = uiReducer(state, { type: "forget", id: "b" });
    expect(state.viewOnly).toBeNull();
    expect(uiReducer(state, { type: "forget", id: "b" })).toBe(state);
  });
});

describe("viewport maths", () => {
  it("fits content inside the view", () => {
    const t = fitTransform({ x: 0, y: 0, width: 1000, height: 500 }, { x: 0, y: 0, width: 520, height: 520 }, 10);
    expect(t.k).toBeCloseTo(0.5);
    expect(t.x).toBeCloseTo(10);
  });

  it("zooms around a fixed screen point", () => {
    const t = zoomAt({ x: 0, y: 0, k: 1 }, 2, 100, 100);
    expect(t).toEqual({ x: -100, y: -100, k: 2 });
  });

  it("maps a dragged-out screen box onto the tree", () => {
    const box = boxBetween({ x: 300, y: 120 }, { x: 100, y: 20 });
    expect(box).toEqual({ x: 100, y: 20, width: 200, height: 100 });
    expect(toTree({ x: 50, y: 20, k: 0.5 }, box)).toEqual({ x: 100, y: 0, width: 400, height: 200 });
  });

  it("tells whether boxes overlap", () => {
    const card = { x: 100, y: 100, width: 200, height: 72 };
    expect(overlaps(card, { x: 290, y: 0, width: 50, height: 110 })).toBe(true);
    expect(overlaps(card, { x: 300, y: 0, width: 50, height: 110 })).toBe(false); // only touching
    expect(overlaps(card, { x: 150, y: 120, width: 10, height: 10 })).toBe(true); // inside
  });

  it("pans just enough to reveal a box", () => {
    const t = panIntoView({ x: 0, y: 0, k: 1 }, { x: 900, y: 10, width: 100, height: 50 }, { x: 0, y: 0, width: 800, height: 600 }, 20);
    expect(t.x).toBe(-220);
    expect(t.y).toBe(10);
  });
});
