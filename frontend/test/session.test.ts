import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Session } from "../src/api/types";
import { SessionProvider, useSession } from "../src/state/session";

const endpoints = vi.hoisted(() => ({ getSession: vi.fn(), signIn: vi.fn(), signOut: vi.fn() }));
vi.mock("../src/api/endpoints", () => endpoints);

const guest = (readPublic: boolean): Session => ({
  role: "guest",
  authenticated: false,
  capabilities: readPublic ? ["read_public"] : [],
  actions: [],
  csrf_token: "guest",
});
const viewer: Session = { role: "public_viewer", authenticated: true, capabilities: ["read_public"], actions: [], csrf_token: "code" };

async function visit(session: Session) {
  endpoints.getSession.mockResolvedValueOnce(session);
  const { result } = renderHook(useSession, { wrapper: SessionProvider });
  await waitFor(() => expect(result.current.session).not.toBeNull());
  return result;
}

describe("access-code prompt", () => {
  beforeEach(() => localStorage.clear());
  afterEach(cleanup);

  it("asks a first-time visitor until they choose the public tree, and remembers that", async () => {
    const first = await visit(guest(true));
    expect(first.current.askForCode).toBe(true);
    act(() => first.current.continueAsGuest?.());
    expect(first.current.askForCode).toBe(false);

    cleanup();
    const second = await visit(guest(true));
    expect(second.current.askForCode).toBe(false);
  });

  it("asks again once a code holder signs out", async () => {
    localStorage.setItem("famtree-guest", "yes");
    const result = await visit(guest(true));
    endpoints.signIn.mockResolvedValueOnce(viewer);
    await act(() => result.current.signIn("code", "ABCD-EFGH"));
    expect(result.current.askForCode).toBe(false);

    endpoints.signOut.mockResolvedValueOnce(guest(true));
    await act(() => result.current.signOut());
    expect(result.current.askForCode).toBe(true);
  });

  it("always asks, with no guest option, while guest access is off", async () => {
    localStorage.setItem("famtree-guest", "yes");
    const result = await visit(guest(false));
    expect(result.current.askForCode).toBe(true);
    expect(result.current.continueAsGuest).toBeNull();
  });
});
