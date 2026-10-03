import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError } from "../api/client";
import * as api from "../api/endpoints";
import { buildIndex, type TreeIndex } from "../lib/treeIndex";
import { useSession } from "./session";

type Status = "loading" | "ready" | "error";

interface TreeState {
  status: Status;
  index: TreeIndex | null;
  error: ApiError | null;
  /** Re-fetch; resolves once the new data is in place. */
  reload: () => Promise<void>;
}

const TreeContext = createContext<TreeState | null>(null);

export function TreeProvider({ children }: { children: ReactNode }) {
  const { session } = useSession();
  const [index, setIndex] = useState<TreeIndex | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<ApiError | null>(null);
  const generation = useRef(0);

  const reload = useCallback(() => {
    const mine = ++generation.current;
    // Responses to superseded requests are ignored.
    return api.getTree().then(
      (data) => {
        if (mine !== generation.current) return;
        setIndex(buildIndex(data));
        setStatus("ready");
        setError(null);
      },
      (err) => {
        if (mine !== generation.current) return;
        setError(err instanceof ApiError ? err : new ApiError(0, "error", String(err)));
        setStatus("error");
      },
    );
  }, []);

  // What a caller may see depends on their role, so refetch when it changes.
  // Guests read nothing while the admin has turned guest access off.
  const role = session?.capabilities.includes("read_public") ? session.role : null;
  useEffect(() => {
    if (role) reload();
  }, [role, reload]);

  const value = useMemo(() => ({ status, index, error, reload }), [status, index, error, reload]);
  return <TreeContext.Provider value={value}>{children}</TreeContext.Provider>;
}

export function useTree(): TreeState {
  const ctx = useContext(TreeContext);
  if (!ctx) throw new Error("useTree outside TreeProvider");
  return ctx;
}
