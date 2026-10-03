import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TreeData } from "../src/api/types";
import { ExportDialog, type ExportView } from "../src/components/export/ExportDialog";
import { buildIndex } from "../src/lib/treeIndex";
import { ToastProvider } from "../src/state/toasts";

const endpoints = vi.hoisted(() => ({ previewExport: vi.fn(), downloadExport: vi.fn() }));
vi.mock("../src/api/endpoints", () => endpoints);

const node = (x: number) => ({ x, y: 0, width: 100, height: 50, row: 0 });
const data: TreeData = {
  people: ["a", "b"].map((id) => ({ id, name: id, attributes: [] })),
  parent_links: [],
  spouse_links: [{ id: "ab", a: "a", b: "b" }],
  definitions: [],
  layout: {
    width: 300,
    height: 100,
    rows: [{ index: 0, top: 0, bottom: 50 }],
    nodes: { a: node(0), b: node(150) },
    connectors: [],
    crossings: [],
  },
};

function open(view: ExportView | null) {
  render(
    <ToastProvider>
      <ExportDialog index={buildIndex(data)} view={view} onClose={() => {}} />
    </ToastProvider>,
  );
  act(() => vi.advanceTimersByTime(400)); // the preview is requested after a pause
}

const lastRequest = () => endpoints.previewExport.mock.lastCall?.[0];
// The dialog's content counts as hidden in jsdom, which does not open modals.
const radio = (name: RegExp) => screen.getByRole<HTMLInputElement>("radio", { name, hidden: true });

describe("exporting the current view", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    endpoints.previewExport.mockReturnValue(new Promise(() => {}));
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("is View Only Selected when that is on, and starts selected", () => {
    open({ window: null, generationsHidden: false, people: ["a"] });
    expect(radio(/current view \(only the selected people\)/i).checked).toBe(true);
    expect(lastRequest()).toMatchObject({ scope: "view", window: null, people: ["a"] });

    fireEvent.click(radio(/full tree/i));
    act(() => vi.advanceTimersByTime(400));
    expect(lastRequest()).toMatchObject({ scope: "full", window: null, people: null });
  });

  it("sends both the generations and the people when both narrow the view", () => {
    const window = { selected_id: "a", above: 0, below: 0 };
    open({ window, generationsHidden: true, people: ["a", "b"] });
    expect(radio(/the selected people, in the generations shown/i).checked).toBe(true);
    expect(lastRequest()).toMatchObject({ scope: "view", window, people: ["a", "b"] });
  });

  it("offers the full tree first when nothing is narrowed", () => {
    open({ window: { selected_id: "a", above: 0, below: 0 }, generationsHidden: false, people: null });
    expect(radio(/generations shown now/i).checked).toBe(false);
    expect(lastRequest()).toMatchObject({ scope: "full", window: null, people: null });
  });
});
