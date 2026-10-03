import { useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import * as api from "../../api/endpoints";
import type { ChangeSet, ParentRole, Ref } from "../../api/types";
import { BIRTH_DATE, LOCATION, PROFESSION } from "../../lib/attributes";
import { localKey, rowsToPayload, type AttributeRow } from "../../lib/attributeRows";
import { draftFrom } from "../../lib/drafts";
import { nameOf, type TreeIndex } from "../../lib/treeIndex";
import { useToast } from "../../state/toasts";
import { useTree } from "../../state/tree";
import { Dialog } from "../ui/Dialog";
import { VisibilityChoice } from "../ui/Visibility";
import { AttributeRows } from "./AttributeRows";
import { PersonPicker, type Picked } from "./PersonPicker";

type Relation = "parent" | "child" | "spouse";

interface Props {
  index: TreeIndex;
  /** Existing person the connection is added to; null adds a new person. */
  anchorId: string | null;
  onClose: () => void;
  onCreated: (personId: string) => void;
}

function quickRows(index: TreeIndex): AttributeRow[] {
  return [BIRTH_DATE, LOCATION, PROFESSION].flatMap((id) => {
    const def = index.definitions.get(id);
    return def ? [{ key: localKey(), definition: { id }, draft: draftFrom(def.value_type, null), isPublic: false }] : [];
  });
}

export function AddDialog({ index, anchorId, onClose, onCreated }: Props) {
  const { reload } = useTree();
  const notify = useToast();
  const isFirst = index.people.size === 0;
  const anchorName = anchorId ? nameOf(index, anchorId) : null;

  const [newName, setNewName] = useState("");
  const [newRows, setNewRows] = useState<AttributeRow[]>(() => quickRows(index));
  const [relation, setRelation] = useState<Relation | null>(null);
  const [other, setOther] = useState<Picked | null>(null);
  const [otherRows, setOtherRows] = useState<AttributeRow[]>(() => quickRows(index));
  const [role, setRole] = useState<ParentRole | null>(null);
  const [isPublic, setIsPublic] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Who is who: "subject" is the anchor (existing) or the new person being added.
  const subjectName = anchorName ?? (newName.trim() || "the new person");
  const otherName = other?.name ?? "the other person";
  const involvesNewPerson = !anchorId || other?.kind === "new";
  // A new person's (required, public) connection must be chosen explicitly;
  // any other new relationship starts private.
  const visibility = isPublic ?? (involvesNewPerson ? null : false);

  // In anchor mode the relation describes the other person ("X's parent");
  // otherwise it describes the new person ("new person is the parent of X").
  const parentIsOther = anchorId ? relation === "parent" : relation === "child";
  const parentName = parentIsOther ? otherName : subjectName;
  const childName = parentIsOther ? subjectName : otherName;

  const summary = useMemo(() => {
    if (!relation || !other) return null;
    const suffix = visibility == null ? "" : visibility ? " (public)" : " (private)";
    if (relation === "spouse") return `${subjectName} and ${otherName} are spouses${suffix}.`;
    return `${parentName} is ${childName}’s ${role ?? "parent"}${suffix}.`;
  }, [relation, other, visibility, subjectName, otherName, parentName, childName, role]);

  const save = async () => {
    setError(null);
    const changes: ChangeSet = { people: [], definitions: [], parent_links: [], spouse_links: [] };
    const addPerson = (ref: string, name: string, rows: AttributeRow[]) => {
      const payload = rowsToPayload(rows, index.definitions);
      if (payload.errors.length) throw new Error(payload.errors.join(" "));
      changes.people!.push({ ref, name, attributes: payload.attributes });
      changes.definitions!.push(...payload.definitions);
    };
    try {
      if (!anchorId) {
        if (!newName.trim()) throw new Error("Enter the new person’s name.");
        addPerson("subject", newName.trim(), newRows);
      }
      if (!isFirst) {
        if (!relation) throw new Error("Choose how the two people are related.");
        if (!other) throw new Error("Choose an existing person or create a new one.");
        if (relation !== "spouse" && !role) throw new Error(`Choose whether ${parentName} is the mother or father.`);
        if (visibility == null) throw new Error("Choose whether this relationship is public or private.");
        if (involvesNewPerson && !visibility) throw new Error("A new person’s connection must be public.");
        if (other.kind === "new") addPerson("other", other.name, otherRows);
        const subject: Ref = anchorId ? { id: anchorId } : { ref: "subject" };
        const target: Ref = other.kind === "existing" ? { id: other.id } : { ref: "other" };
        if (relation === "spouse") {
          changes.spouse_links!.push({ a: subject, b: target, is_public: visibility });
        } else {
          const [parent, child] = parentIsOther ? [target, subject] : [subject, target];
          changes.parent_links!.push({ parent, child, role: role!, is_public: visibility });
        }
      }
    } catch (err) {
      setError((err as Error).message);
      return;
    }

    setSaving(true);
    try {
      const { created } = await api.applyChanges(changes);
      await reload();
      notify("Saved.", "success");
      onCreated(created.subject ?? anchorId ?? created.other);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  };

  const title = isFirst ? "Add the first person" : anchorId ? `Add a connection for ${anchorName}` : "Add a person";
  const exclude = anchorId ? [anchorId] : [];

  return (
    <Dialog
      title={title}
      onClose={onClose}
      size="wide"
      footer={
        <>
          <button type="button" className="button" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="button" className="button button--primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <form
        className="add-form"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        {!anchorId && (
          <section>
            <div className="field">
              <label htmlFor="new-person-name">Name (always public)</label>
              <input id="new-person-name" autoFocus value={newName} maxLength={200} onChange={(e) => setNewName(e.target.value)} />
            </div>
            <details>
              <summary>More details (optional, private unless you choose otherwise)</summary>
              <AttributeRows rows={newRows} definitions={index.definitions} onChange={setNewRows} />
            </details>
          </section>
        )}

        {isFirst ? (
          <p className="hint">The first person needs no connection. Everyone added after this is connected to someone already in the tree.</p>
        ) : (
          <section>
            <fieldset className="choice">
              <legend>{anchorId ? `Who are you adding for ${anchorName}?` : `${subjectName} is the…`}</legend>
              {(["parent", "child", "spouse"] as Relation[]).map((r) => (
                <label key={r}>
                  <input type="radio" name="relation" checked={relation === r} onChange={() => setRelation(r)} />
                  {anchorId ? `${anchorName}’s ${r}` : `${r} of…`}
                </label>
              ))}
            </fieldset>

            <PersonPicker
              label={anchorId ? "Their name" : "The other person"}
              value={other}
              onChange={setOther}
              exclude={exclude}
              autoFocus={Boolean(anchorId)}
            />
            {other?.kind === "new" && (
              <details>
                <summary>Details for {other.name} (optional)</summary>
                <AttributeRows rows={otherRows} definitions={index.definitions} onChange={setOtherRows} />
              </details>
            )}

            {relation && relation !== "spouse" && (
              <fieldset className="choice">
                <legend>
                  The parent is <strong>{parentName}</strong>. Is {parentName} the child’s mother or father?
                </legend>
                <label>
                  <input type="radio" name="role" checked={role === "mother"} onChange={() => setRole("mother")} /> Mother
                </label>
                <label>
                  <input type="radio" name="role" checked={role === "father"} onChange={() => setRole("father")} /> Father
                </label>
              </fieldset>
            )}

            <VisibilityChoice
              label="Is this relationship public?"
              value={visibility}
              onChange={setIsPublic}
              privateDisabledReason={
                involvesNewPerson
                  ? "Every new person needs at least one public connection, so this one must be public."
                  : undefined
              }
            />
            {visibility && (
              <p className="consequence">
                Anyone, including guests, will see this connection, and therefore that {subjectName} and {otherName} are
                both in the tree.
              </p>
            )}
            {summary && <p className="summary">Saving will record: {summary}</p>}
          </section>
        )}
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        <button type="submit" hidden />
      </form>
    </Dialog>
  );
}
