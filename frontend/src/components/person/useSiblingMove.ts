import { useCallback, useState } from "react";
import { ApiError } from "../../api/client";
import * as api from "../../api/endpoints";
import { siblingMove, type Direction } from "../../lib/siblings";
import { nameOf, type TreeIndex } from "../../lib/treeIndex";
import { useToast } from "../../state/toasts";
import { useTree } from "../../state/tree";

/** Moves a card one place left or right among its siblings and reloads the tree. */
export function useSiblingMove(index: TreeIndex | null) {
  const { reload } = useTree();
  const notify = useToast();
  const [busy, setBusy] = useState(false);

  const move = useCallback(
    async (id: string, direction: Direction) => {
      const order = index && siblingMove(index, id, direction);
      if (!index || !order) return;
      setBusy(true);
      try {
        await api.setSiblingOrder(order);
        await reload();
        notify(`Moved ${nameOf(index, id)} ${direction}.`, "success");
      } catch (err) {
        const stale = err instanceof ApiError && err.isStale;
        const message = err instanceof ApiError ? err.message : "Could not move them.";
        notify(stale ? `${message} The tree has been reloaded.` : message, "error");
        if (stale) await reload();
      } finally {
        setBusy(false);
      }
    },
    [index, reload, notify],
  );

  return { move, busy };
}
