import { useId, useState } from "react";
import type { AttributeDefinition, ValueType } from "../../api/types";
import { VALUE_TYPE_LABELS } from "../../lib/attributes";
import { localKey, rowLabel, type AttributeRow } from "../../lib/attributeRows";
import { draftFrom } from "../../lib/drafts";
import { VisibilityChoice } from "../ui/Visibility";
import { ValueInput } from "./ValueInput";

interface Props {
  rows: AttributeRow[];
  definitions: Map<string, AttributeDefinition>;
  onChange: (rows: AttributeRow[]) => void;
}

const NEW = "__new__";

/** Attribute values with per-value visibility. New values start private. */
export function AttributeRows({ rows, definitions, onChange }: Props) {
  const [adding, setAdding] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newType, setNewType] = useState<ValueType>("text");
  const selectId = useId();

  const used = new Set(rows.flatMap((r) => ("id" in r.definition ? [r.definition.id] : [])));
  const available = [...definitions.values()].filter((d) => !used.has(d.id));
  const update = (key: string, patch: Partial<AttributeRow>) =>
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const addExisting = (definition: AttributeDefinition) => {
    onChange([
      ...rows,
      { key: localKey(), definition: { id: definition.id }, draft: draftFrom(definition.value_type, null), isPublic: false },
    ]);
    setAdding("");
  };

  const addNew = () => {
    const label = newLabel.trim();
    if (!label) return;
    const ref = localKey("def");
    onChange([
      ...rows,
      { key: localKey(), definition: { ref, label, value_type: newType }, draft: draftFrom(newType, null), isPublic: false },
    ]);
    setAdding("");
    setNewLabel("");
  };

  return (
    <div className="attribute-rows">
      {rows.map((row) => (
        <div key={row.key} className="attribute-row">
          <ValueInput label={rowLabel(row, definitions)} draft={row.draft} onChange={(draft) => update(row.key, { draft })} />
          <div className="attribute-row__side">
            <VisibilityChoice compact label={`${rowLabel(row, definitions)} visibility`} value={row.isPublic} onChange={(isPublic) => update(row.key, { isPublic })} />
            <button
              type="button"
              className="link-button"
              onClick={() => onChange(rows.filter((r) => r.key !== row.key))}
              aria-label={`Remove ${rowLabel(row, definitions)}`}
            >
              Remove
            </button>
          </div>
        </div>
      ))}

      <div className="attribute-add">
        <label className="sr-only" htmlFor={selectId}>
          Add a detail
        </label>
        <select
          id={selectId}
          value={adding}
          onChange={(event) => {
            const value = event.target.value;
            const definition = definitions.get(value);
            if (definition) addExisting(definition);
            else setAdding(value);
          }}
        >
          <option value="">+ Add a detail…</option>
          {available.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
          <option value={NEW}>New kind of detail…</option>
        </select>
        {adding === NEW && (
          <div className="attribute-new">
            <input
              aria-label="Name of the new detail"
              placeholder="e.g. Nickname"
              value={newLabel}
              maxLength={60}
              onChange={(e) => setNewLabel(e.target.value)}
            />
            <select aria-label="Type of the new detail" value={newType} onChange={(e) => setNewType(e.target.value as ValueType)}>
              {Object.entries(VALUE_TYPE_LABELS).map(([type, label]) => (
                <option key={type} value={type}>
                  {label}
                </option>
              ))}
            </select>
            <button type="button" className="button" onClick={addNew} disabled={!newLabel.trim()}>
              Add
            </button>
            <small className="hint">It will be available for everyone in the tree.</small>
          </div>
        )}
      </div>
    </div>
  );
}
