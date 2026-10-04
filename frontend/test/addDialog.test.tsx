import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TreeData } from "../src/api/types";
import { AddDialog } from "../src/components/person/AddDialog";
import { GENDER } from "../src/lib/attributes";
import { buildIndex } from "../src/lib/treeIndex";

const endpoints = vi.hoisted(() => ({ searchPeople: vi.fn(), applyChanges: vi.fn() }));
vi.mock("../src/api/endpoints", () => endpoints);
vi.mock("../src/state/tree", () => ({ useTree: () => ({ reload: vi.fn() }) }));
vi.mock("../src/state/toasts", () => ({ useToast: () => vi.fn() }));

afterEach(cleanup);

const data: TreeData = {
  people: [
    { id: "mom", name: "Mom", attributes: [{ definition_id: GENDER, value: "female" }], revision: 1 },
    { id: "dad", name: "Dad", attributes: [{ definition_id: GENDER, value: "male" }], revision: 1 },
    { id: "kid", name: "Kid", attributes: [], revision: 1 },
  ],
  parent_links: [],
  spouse_links: [],
  definitions: [{ id: GENDER, label: "Gender", value_type: "gender", builtin: true }],
  layout: { width: 0, height: 0, rows: [], nodes: {}, connectors: [], crossings: [] },
};
const index = buildIndex(data);

const role = (name: "Mother" | "Father") => (screen.getByLabelText(name) as HTMLInputElement).checked;

function open(anchorId: string) {
  render(<AddDialog index={index} anchorId={anchorId} onClose={() => {}} onCreated={() => {}} />);
}

describe("adding a child or parent", () => {
  it("preselects mother or father from the parent's recorded gender", () => {
    open("mom");
    fireEvent.click(screen.getByLabelText("Mom’s child"));
    expect([role("Mother"), role("Father")]).toEqual([true, false]);
    expect(screen.getByText(/Chosen from Mom’s recorded gender/)).toBeTruthy();
  });

  it("keeps the editor's own choice for that parent", () => {
    open("mom");
    fireEvent.click(screen.getByLabelText("Mom’s child"));
    fireEvent.click(screen.getByLabelText("Father"));
    expect([role("Mother"), role("Father")]).toEqual([false, true]);
    expect(screen.queryByText(/recorded gender/)).toBeNull();
    // A different parent (whoever is chosen as Mom's parent) starts afresh.
    fireEvent.click(screen.getByLabelText("Mom’s parent"));
    expect([role("Mother"), role("Father")]).toEqual([false, false]);
    fireEvent.click(screen.getByLabelText("Mom’s child"));
    expect([role("Mother"), role("Father")]).toEqual([false, true]);
  });

  it("follows the gender of an existing person chosen as the parent", async () => {
    endpoints.searchPeople.mockResolvedValue({ results: [{ id: "dad", name: "Dad", context: [] }] });
    open("kid");
    fireEvent.click(screen.getByLabelText("Kid’s parent"));
    expect([role("Mother"), role("Father")]).toEqual([false, false]);
    fireEvent.change(screen.getByLabelText("Their name"), { target: { value: "Da" } });
    // In jsdom the dialog is not open, so its contents count as hidden.
    fireEvent.click(await screen.findByRole("option", { name: "Dad", hidden: true }));
    expect([role("Mother"), role("Father")]).toEqual([false, true]);
  });

  it("follows the gender entered for a new person", () => {
    render(<AddDialog index={index} anchorId={null} onClose={() => {}} onCreated={() => {}} />);
    fireEvent.change(screen.getByLabelText("Name (always public)"), { target: { value: "Gran" } });
    fireEvent.click(screen.getByLabelText("parent of…"));
    expect([role("Mother"), role("Father")]).toEqual([false, false]);
    fireEvent.change(screen.getByLabelText("Gender"), { target: { value: "female" } });
    expect([role("Mother"), role("Father")]).toEqual([true, false]);
  });
});
