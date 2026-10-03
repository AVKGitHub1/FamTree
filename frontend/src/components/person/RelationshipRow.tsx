import { useState } from "react";
import { ApiError } from "../../api/client";
import * as api from "../../api/endpoints";
import type { ParentLink, ParentRole, SpouseLink } from "../../api/types";
import { nameOf, type TreeIndex } from "../../lib/treeIndex";
import { useToast } from "../../state/toasts";
import { useTree } from "../../state/tree";
import { VisibilityBadge } from "../ui/Visibility";

type Props =
  | { kind: "parent"; link: ParentLink; otherId: string; caption: string; editable: boolean; index: TreeIndex; onSelect: (id: string) => void }
  | { kind: "spouse"; link: SpouseLink; otherId: string; caption: string; editable: boolean; index: TreeIndex; onSelect: (id: string) => void };

export function publicConsequence(index: TreeIndex, kind: "parent" | "spouse", link: ParentLink | SpouseLink): string {
  if (kind === "parent") {
    const l = link as ParentLink;
    return `Anyone, including guests, will see that ${nameOf(index, l.parent_id)} is ${nameOf(index, l.child_id)}’s ${l.role}.`;
  }
  const l = link as SpouseLink;
  return `Anyone, including guests, will see that ${nameOf(index, l.a)} and ${nameOf(index, l.b)} are spouses.`;
}

/** One relationship in the details panel; editors can change it in place. */
export function RelationshipRow(props: Props) {
  const { kind, link, otherId, caption, editable, index, onSelect } = props;
  const { reload } = useTree();
  const notify = useToast();
  const [confirming, setConfirming] = useState<"public" | "remove" | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    try {
      await action();
      await reload();
      notify(success, "success");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not save the change.";
      notify(err instanceof ApiError && err.isStale ? `${message} The tree has been reloaded.` : message, "error");
      if (err instanceof ApiError && err.isStale) await reload();
    } finally {
      setBusy(false);
      setConfirming(null);
    }
  };

  const revision = link.revision ?? 0;
  const setVisibility = (isPublic: boolean) =>
    run(
      () =>
        kind === "parent"
          ? api.updateParentLink(link.id, { expected_revision: revision, is_public: isPublic })
          : api.updateSpouseLink(link.id, { expected_revision: revision, is_public: isPublic }),
      isPublic ? "Relationship is now public." : "Relationship is now private.",
    );
  const setRole = (role: ParentRole) =>
    run(() => api.updateParentLink(link.id, { expected_revision: revision, role }), "Role updated.");
  const remove = () => run(() => api.deleteRelationship(kind, link.id, revision), "Relationship removed.");

  return (
    <li className="relationship">
      <div className="relationship__main">
        <button type="button" className="link-button" onClick={() => onSelect(otherId)}>
          {nameOf(index, otherId)}
        </button>
        <span className="relationship__caption">{caption}</span>
        <VisibilityBadge isPublic={link.is_public} />
      </div>
      {editable && (
        <div className="relationship__edit">
          {kind === "parent" && (
            <label>
              <span className="sr-only">Parent’s role</span>
              <select
                value={(link as ParentLink).role}
                disabled={busy}
                onChange={(e) => setRole(e.target.value as ParentRole)}
                aria-label={`Role of ${nameOf(index, (link as ParentLink).parent_id)} as parent`}
              >
                <option value="mother">Mother</option>
                <option value="father">Father</option>
              </select>
            </label>
          )}
          {link.is_public ? (
            <button type="button" className="link-button" disabled={busy} onClick={() => setVisibility(false)}>
              Make private
            </button>
          ) : (
            <button type="button" className="link-button" disabled={busy} onClick={() => setConfirming("public")}>
              Make public
            </button>
          )}
          <button type="button" className="link-button link-button--danger" disabled={busy} onClick={() => setConfirming("remove")}>
            Remove
          </button>
        </div>
      )}
      {confirming && (
        <div className="confirm" role="alertdialog" aria-label="Confirm change">
          <p>
            {confirming === "public"
              ? publicConsequence(index, kind, link)
              : `Remove this relationship? The people themselves are kept.`}
          </p>
          <button type="button" className="button button--primary" disabled={busy} onClick={() => (confirming === "public" ? setVisibility(true) : remove())}>
            {confirming === "public" ? "Make public" : "Remove"}
          </button>
          <button type="button" className="button" disabled={busy} onClick={() => setConfirming(null)}>
            Cancel
          </button>
        </div>
      )}
    </li>
  );
}
