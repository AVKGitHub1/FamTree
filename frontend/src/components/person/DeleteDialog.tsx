import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import * as api from "../../api/endpoints";
import type { DeletionPreview } from "../../api/types";
import { nameOf, spouseOther, type TreeIndex } from "../../lib/treeIndex";
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
 * would leave someone without a public relationship. */
export function DeleteDialog({ index, personId, onClose, onDeleted }: Props) {
  const { reload } = useTree();
  const notify = useToast();
  const [preview, setPreview] = useState<DeletionPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const person = index.people.get(personId);

  useEffect(() => {
    api.getDeletionPreview(personId).then(setPreview, (err) =>
      setError(err instanceof ApiError ? err.message : "Could not check this deletion."),
    );
  }, [personId]);

  const descriptions = [
    ...(index.parentsOf.get(personId) ?? []).map((l) => `${nameOf(index, l.parent_id)} is their ${l.role}`),
    ...(index.childrenOf.get(personId) ?? []).map((l) => `parent (${l.role}) of ${nameOf(index, l.child_id)}`),
    ...(index.spousesOf.get(personId) ?? []).map((l) => `spouse of ${nameOf(index, spouseOther(l, personId))}`),
  ];

  const remove = async () => {
    setBusy(true);
    try {
      await api.deletePerson(personId, person?.revision ?? 0);
      await reload();
      notify(`${person?.name ?? "Person"} was deleted.`, "success");
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete.");
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
                {descriptions.map((text) => (
                  <li key={text}>{text}</li>
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
