import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { ApiError } from "../src/api/client";
import type { RelationOutcome, Session, TreeData } from "../src/api/types";
import type { TreeIndex } from "../src/lib/treeIndex";

const endpoints = vi.hoisted(() => ({
  getSession: vi.fn(),
  signIn: vi.fn(),
  signOut: vi.fn(),
  getTree: vi.fn(),
  calculateRelation: vi.fn(),
}));
vi.mock("../src/api/endpoints", () => endpoints);

// The real viewport needs layout measurements that jsdom does not provide.
vi.mock("../src/components/tree/TreeView", () => ({
  TreeView: ({ index, onActivate, describe }: { index: TreeIndex; onActivate: (id: string) => void; describe: (id: string) => string }) => (
    <ul>
      {[...index.people.keys()].map((id) => (
        <li key={id}>
          <button type="button" onClick={() => onActivate(id)}>
            {describe(id)}
          </button>
        </li>
      ))}
    </ul>
  ),
}));


const actions = ["calculate_relation", "export"] as const;
const familyViewer: Session = {
  role: "private_viewer",
  authenticated: true,
  capabilities: ["read_public", "read_private"],
  actions: [...actions],
  csrf_token: "viewer",
};
const guest: Session = { role: "guest", authenticated: false, capabilities: ["read_public"], actions: [...actions], csrf_token: "guest" };

const node = (row: number, x = 0) => ({ x, y: row * 100, width: 100, height: 50, row });
function tree(full: boolean): TreeData {
  return {
    people: [
      { id: "p", name: "Parent", attributes: full ? [{ definition_id: "profession", value: "Secret job" }] : [] },
      { id: "r", name: "Relative", attributes: [] },
    ],
    parent_links: full ? [{ id: "l", parent_id: "p", child_id: "r", role: "father" }] : [],
    spouse_links: [],
    definitions: full ? [{ id: "profession", label: "Profession", value_type: "text", builtin: true }] : [],
    layout: {
      width: 300,
      height: 200,
      rows: [0, 1].map((index) => ({ index, top: index * 100, bottom: index * 100 + 50 })),
      nodes: full ? { p: node(0), r: node(1) } : { p: node(0), r: node(0, 150) },
      connectors: [],
      crossings: [],
    },
  };
}
const father: RelationOutcome = {
  a: "p",
  b: "r",
  message: null,
  results: [
    {
      kind: "parent",
      label: "father",
      statement: "Parent is Relative's father",
      distance_a: 0,
      distance_b: 1,
      cousin_degree: null,
      removed: null,
      common_ancestors: [],
      path: [],
    },
  ],
};

async function signOutAndContinueAsGuest() {
  endpoints.signOut.mockResolvedValueOnce(guest);
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  fireEvent.click(await screen.findByRole("button", { name: "Continue without a code" }));
}

describe("changing access in the same browser", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetAllMocks();
    window.matchMedia = ((query: string) =>
      ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} }) as unknown as MediaQueryList) as typeof window.matchMedia;
    endpoints.getSession.mockResolvedValue(familyViewer);
  });
  afterEach(cleanup);

  it("does not keep showing the private tree when the public one fails to load", async () => {
    endpoints.getTree.mockResolvedValueOnce(tree(true));
    render(<App />);
    expect(await screen.findByText(/Secret job/)).toBeTruthy();

    endpoints.getTree.mockRejectedValueOnce(new ApiError(0, "error", "The network is down."));
    await signOutAndContinueAsGuest();
    expect(await screen.findByText("Could not load the tree")).toBeTruthy();
    expect(screen.queryByText(/Secret job/)).toBeNull();
    expect(screen.queryByText(/Parent/)).toBeNull();
  });

  it("drops a relation result calculated with the previous access", async () => {
    endpoints.getTree.mockResolvedValueOnce(tree(true));
    endpoints.calculateRelation.mockResolvedValueOnce(father);
    render(<App />);
    await screen.findByText(/Secret job/);
    fireEvent.click(screen.getByRole("button", { name: "Calculate Relation" }));
    fireEvent.click(screen.getByRole("button", { name: /^Parent/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Relative/ }));
    expect(await screen.findByText("Parent is Relative's father")).toBeTruthy();

    endpoints.getTree.mockResolvedValueOnce(tree(false));
    await signOutAndContinueAsGuest();
    await screen.findByRole("button", { name: /^Relative/ });
    expect(screen.queryByText("Parent is Relative's father")).toBeNull();
    expect(screen.queryByText(/Secret job/)).toBeNull();
    expect(endpoints.calculateRelation).toHaveBeenCalledTimes(1);
  });
});
