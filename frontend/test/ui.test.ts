import { describe, expect, it } from "vitest";
import { initialUi, uiReducer, type UiState } from "../src/state/ui";
import { fitTransform, panIntoView, zoomAt } from "../src/lib/viewport";

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

  it("starts from the card shortcut with the first person chosen", () => {
    const state = uiReducer(initialUi, { type: "relationStart", first: "x" });
    expect(state.relation).toEqual({ stage: "pick", first: "x" });
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

  it("pans just enough to reveal a box", () => {
    const t = panIntoView({ x: 0, y: 0, k: 1 }, { x: 900, y: 10, width: 100, height: 50 }, { x: 0, y: 0, width: 800, height: 600 }, 20);
    expect(t.x).toBe(-220);
    expect(t.y).toBe(10);
  });
});
