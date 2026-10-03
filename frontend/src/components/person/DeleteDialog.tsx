import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import * as api from "../../api/endpoints";
import type { DeletionPreview } from "../../api/types";
import type { TreeIndex } from "../../lib/treeIndex";
import { useToast } from "../../state/toasts";
import { useTree } from "../../state/tree";
import { Dialog } from "../ui/Dialog";

interface Props {
  index: TreeIndex;
  personId: string;
  onClose: () => void;
  onDeleted: () => void;
}

/** Shows which relationships go with the person, and refuses deletions that
 * would leave someone without a public relationship. The list comes from the
 * server's preview, and the deletion is bound to it: if someone changes these
 * relationships meanwhile, the list is refreshed for review instead. */
export function DeleteDialog({ index, personId, onClose, onDeleted }: Props) {
  const { reload } = useTree();
  const notify = useToast();
  const [preview, setPreview] = useState<DeletionPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const person = index.people.get(personId);

  const check = useCallback(
    () =>
      api.getDeletionPreview(personId).then(setPreview, (err) =>
        setError(err instanceof ApiError ? err.message : "Could not check this deletion."),
      ),
    [personId],
  );
  useEffect(() => {
    check();
  }, [check]);

  const descriptions = preview
    ? [
        ...preview.parent_links.map((l) =>
          l.child.id === personId ? `${l.parent.name} is their ${l.role}` : `parent (${l.role}) of ${l.child.name}`,
        ),
        ...preview.spouse_links.map((l) => `spouse of ${l.spouse.name}`),
      ]
    : [];

  const remove = async () => {
    if (!preview) return;
    setBusy(true);
    try {
      await api.deletePerson(personId, person?.revision ?? 0, preview.relationships);
      await reload();
      notify(`${person?.name ?? "Person"} was deleted.`, "success");
      onDeleted();
    } catch (err) {
      const stale = err instanceof ApiError && err.isStale;
      setError(err instanceof ApiError ? err.message : "Could not delete.");
      if (stale) {
        setPreview(null);
        await Promise.all([check(), reload()]);
      }
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={`Delete ${person?.name ?? "person"}?`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="button" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="button button--danger"
            disabled={!preview?.allowed || busy}
            onClick={remove}
          >
            Delete
          </button>
        </>
      }
    >
      {!preview && !error && <p>Checking…</p>}
      {preview && (
        <>
          {descriptions.length > 0 ? (
            <>
              <p>These relationships will be removed too:</p>
              <ul>
                {descriptions.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
            </>
          ) : (
            <p>This person has no recorded relationships.</p>
          )}
          {!preview.allowed && (
            <div className="error-banner" role="alert">
              <p>
                This would leave{" "}
                {preview.blocked_people.map((p) => p.name).join(", ")} without any public relationship. Connect them to
                someone else publicly first.
              </p>
            </div>
          )}
        </>
      )}
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
}
