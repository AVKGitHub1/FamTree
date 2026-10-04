import { useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import * as api from "../../api/endpoints";
import type { Person } from "../../api/types";
import { attributeOf, displayValue, PROFILE_PIC, profilePicture } from "../../lib/attributes";
import { rowsFromPerson, rowsToPayload, type AttributeRow } from "../../lib/attributeRows";
import { nameKey } from "../../lib/namesakes";
import { siblingMove } from "../../lib/siblings";
import { spouseOther, type TreeIndex } from "../../lib/treeIndex";
import { useToast } from "../../state/toasts";
import { useTree } from "../../state/tree";
import { VisibilityBadge } from "../ui/Visibility";
import { AttributeRows } from "./AttributeRows";
import { NamesakeWarning } from "./NamesakeWarning";
import { RelationshipRow } from "./RelationshipRow";
import { useSiblingMove } from "./useSiblingMove";

interface Props {
  index: TreeIndex;
  person: Person;
  canEdit: boolean;
  onSelect: (id: string) => void;
  onAddConnection: (id: string) => void;
  onRelation: (id: string) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}

export function PersonPanel({ index, person, canEdit, onSelect, onAddConnection, onRelation, onDelete, onClose }: Props) {
  const [editing, setEditing] = useState(false);
  const parents = index.parentsOf.get(person.id) ?? [];
  const children = index.childrenOf.get(person.id) ?? [];
  const spouses = index.spousesOf.get(person.id) ?? [];
  const picture = profilePicture(person, index.definitions);
  const { move, busy: moving } = useSiblingMove(index);
  const canMoveLeft = canEdit && siblingMove(index, person.id, "left") != null;
  const canMoveRight = canEdit && siblingMove(index, person.id, "right") != null;

  return (
    <aside className="panel" aria-label={`Details for ${person.name}`}>
      <div className="panel__header">
        <h2>{person.name}</h2>
        <button type="button" className="icon-button" aria-label="Close details" onClick={onClose}>
          ×
        </button>
      </div>

      {editing ? (
        // Keyed by revision: loading a newer version starts the form afresh from it.
        <PersonEditor key={person.revision} index={index} person={person} onDone={() => setEditing(false)} />
      ) : (
        <>
          {picture && (
            <figure className="panel__picture">
              <img className="avatar avatar--panel" src={api.pictureUrl(person.id, picture.id, "full")} alt={`Picture of ${person.name}`} />
              <figcaption>
                <VisibilityBadge isPublic={attributeOf(person, PROFILE_PIC)?.is_public} />
              </figcaption>
            </figure>
          )}
          <dl className="facts">
            {person.attributes.map((attr) => {
              const def = index.definitions.get(attr.definition_id);
              if (!def || def.value_type === "image") return null;
              return (
                <div key={attr.definition_id} className="facts__row">
                  <dt>{def.label}</dt>
                  <dd>
                    {def.value_type === "url" ? (
                      <a href={String(attr.value)} target="_blank" rel="noopener noreferrer nofollow">
                        {String(attr.value)}
                      </a>
                    ) : (
                      <span className={def.value_type === "long_text" ? "preserve-lines" : undefined}>
                        {displayValue(def.value_type, attr.value)}
                      </span>
                    )}{" "}
                    <VisibilityBadge isPublic={attr.is_public} />
                  </dd>
                </div>
              );
            })}
            {person.attributes.length === 0 && <p className="muted">No details recorded{canEdit ? " yet" : ""}.</p>}
          </dl>
          <div className="panel__actions">
            <button type="button" className="button" onClick={() => onRelation(person.id)}>
              Calculate relation…
            </button>
            {canEdit && (
              <>
                <button type="button" className="button button--primary" onClick={() => setEditing(true)}>
                  Edit details
                </button>
                <button type="button" className="button" onClick={() => onAddConnection(person.id)}>
                  Add connection…
                </button>
              </>
            )}
          </div>
          {(canMoveLeft || canMoveRight) && (
            <div className="panel__order" role="group" aria-label={`Place of ${person.name} among their siblings`}>
              <span className="muted">Among their siblings:</span>
              <button type="button" className="button" disabled={!canMoveLeft || moving} onClick={() => void move(person.id, "left")}>
                ← Move left
              </button>
              <button type="button" className="button" disabled={!canMoveRight || moving} onClick={() => void move(person.id, "right")}>
                Move right →
              </button>
            </div>
          )}
        </>
      )}

      <section className="relationships" aria-label="Relationships">
        <RelationshipGroup title="Parents" empty="No parents shown.">
          {parents.map((link) => (
            <RelationshipRow key={link.id} kind="parent" link={link} otherId={link.parent_id} caption={link.role} editable={canEdit} index={index} onSelect={onSelect} />
          ))}
        </RelationshipGroup>
        <RelationshipGroup title="Spouses" empty="No spouses shown.">
          {spouses.map((link) => (
            <RelationshipRow key={link.id} kind="spouse" link={link} otherId={spouseOther(link, person.id)} caption="spouse" editable={canEdit} index={index} onSelect={onSelect} />
          ))}
        </RelationshipGroup>
        <RelationshipGroup title="Children" empty="No children shown.">
          {children.map((link) => (
            <RelationshipRow key={link.id} kind="parent" link={link} otherId={link.child_id} caption={`child (${person.name} is ${link.role})`} editable={canEdit} index={index} onSelect={onSelect} />
          ))}
        </RelationshipGroup>
      </section>

      {canEdit && !editing && (
        <div className="panel__danger">
          <button type="button" className="link-button link-button--danger" onClick={() => onDelete(person.id)}>
            Delete {person.name}…
          </button>
        </div>
      )}
    </aside>
  );
}

function RelationshipGroup({ title, empty, children }: { title: string; empty: string; children: React.ReactNode[] }) {
  return (
    <div className="relationship-group">
      <h3>{title}</h3>
      {children.length ? <ul>{children}</ul> : <p className="muted">{empty}</p>}
    </div>
  );
}

function PersonEditor({ index, person, onDone }: { index: TreeIndex; person: Person; onDone: () => void }) {
  const { reload } = useTree();
  const notify = useToast();
  const [name, setName] = useState(person.name);
  const self = useMemo(() => [person.id], [person.id]);
  const [rows, setRows] = useState<AttributeRow[]>(() => rowsFromPerson(person, index.definitions));
  const [error, setError] = useState<{ message: string; stale: boolean } | null>(null);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    const payload = rowsToPayload(rows, index.definitions);
    if (!name.trim()) return setError({ message: "A name is required.", stale: false });
    if (payload.errors.length) return setError({ message: payload.errors.join(" "), stale: false });
    setSaving(true);
    try {
      await api.updatePerson(person.id, {
        expected_revision: person.revision ?? 0,
        name: name.trim(),
        attributes: payload.attributes,
        definitions: payload.definitions,
      });
      await reload();
      notify("Saved.", "success");
      onDone();
    } catch (err) {
      const apiError = err instanceof ApiError ? err : null;
      setError({ message: apiError?.message ?? "Could not save.", stale: Boolean(apiError?.isStale) });
    } finally {
      setSaving(false);
    }
  };

  // Stale save: load the latest version (remounting this form) so the editor
  // can reconcile by re-applying their change to current data.
  const loadLatest = async () => {
    await reload();
    notify("Loaded the latest version. Re-apply your changes and save again.", "info");
  };

  return (
    <form
      className="editor"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <div className="field">
        <label htmlFor={`name-${person.id}`}>Name (always public)</label>
        <input id={`name-${person.id}`} value={name} maxLength={200} required onChange={(e) => setName(e.target.value)} />
      </div>
      {nameKey(name) !== nameKey(person.name) && (
        <NamesakeWarning
          index={index}
          name={name}
          exclude={self}
          advice="Two people may share a name, but check that this is not the same person entered twice."
        />
      )}
      <AttributeRows rows={rows} definitions={index.definitions} onChange={setRows} />
      {error && (
        <div className="error-banner" role="alert">
          <p>{error.message}</p>
          {error.stale && (
            <button type="button" className="button" onClick={loadLatest}>
              Load latest version
            </button>
          )}
        </div>
      )}
      <div className="editor__actions">
        <button type="submit" className="button button--primary" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button type="button" className="button" onClick={onDone} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  );
}
