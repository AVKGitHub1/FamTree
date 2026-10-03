import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, onCsrfRejected, setCsrfToken } from "../api/client";
import * as api from "../api/endpoints";
import type { Action, Session } from "../api/types";

interface SessionState {
  session: Session | null;
  /** Set when the server's storage is unavailable or unreachable. */
  error: ApiError | null;
  refresh: () => Promise<void>;
  signIn: (kind: "code" | "admin", secret: string) => Promise<void>;
  signOut: () => Promise<void>;
  can: (action: Action) => boolean;
  /** Not signed in, and either guests may not read the tree or this browser
   * has not chosen to browse without a code. */
  askForCode: boolean;
  /** null unless the visitor is a guest and the admin allows guest access. */
  continueAsGuest: (() => void) | null;
}

const SessionContext = createContext<SessionState | null>(null);

const GUEST_KEY = "famtree-guest";

function storedGuestChoice(): boolean {
  try {
    return localStorage.getItem(GUEST_KEY) === "yes";
  } catch {
    return false;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [guestChosen, setGuestChosen] = useState(storedGuestChoice);

  const chooseGuest = useCallback((chosen: boolean) => {
    setGuestChosen(chosen);
    try {
      if (chosen) localStorage.setItem(GUEST_KEY, "yes");
      else localStorage.removeItem(GUEST_KEY);
    } catch {
      // Storage may be unavailable (private mode); the choice still applies now.
    }
  }, []);

  const adopt = useCallback((next: Session) => {
    setCsrfToken(next.csrf_token);
    setSession(next);
    setError(null);
  }, []);

  const refresh = useCallback(
    () =>
      api.getSession().then(adopt, (err) =>
        setError(err instanceof ApiError ? err : new ApiError(0, "error", String(err))),
      ),
    [adopt],
  );

  useEffect(() => {
    onCsrfRejected(refresh);
    refresh();
  }, [refresh]);

  const value = useMemo<SessionState>(() => {
    const guest = session != null && !session.authenticated;
    const guestMayRead = guest && session.capabilities.includes("read_public");
    return {
      session,
      error,
      refresh,
      signIn: async (kind, secret) => {
        adopt(await api.signIn(kind, secret));
        // Code holders are asked for their code again once the session ends.
        chooseGuest(false);
      },
      signOut: async () => adopt(await api.signOut()),
      can: (action) => session?.actions.includes(action) ?? false,
      askForCode: guest && !(guestMayRead && guestChosen),
      continueAsGuest: guestMayRead ? () => chooseGuest(true) : null,
    };
  }, [session, error, refresh, adopt, guestChosen, chooseGuest]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession outside SessionProvider");
  return ctx;
}

export const ROLE_LABELS: Record<Session["role"], string> = {
  guest: "Guest",
  public_viewer: "Viewer",
  private_viewer: "Family viewer",
  editor: "Editor",
  admin: "Admin",
};
