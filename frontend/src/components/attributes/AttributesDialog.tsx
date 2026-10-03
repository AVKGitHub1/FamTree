import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import * as api from "../../api/endpoints";
import type { AttributeDefinition, ValueType } from "../../api/types";
import { CUSTOM_VALUE_TYPES, VALUE_TYPE_LABELS } from "../../lib/attributes";
import { useToast } from "../../state/toasts";
import { useTree } from "../../state/tree";
import { Dialog } from "../ui/Dialog";

/** Reusable detail definitions. Renaming keeps values; incompatible type
 * changes are refused by the server while values exist. */
export function AttributesDialog({ onClose }: { onClose: () => void }) {
  const notify = useToast();
  const { reload } = useTree();
  const [definitions, setDefinitions] = useState<AttributeDefinition[] | null>(null);
  const [label, setLabel] = useState("");
  const [type, setType] = useState<ValueType>("text");

  const load = useCallback(
    () =>
      api.listDefinitions().then(
        (r) => setDefinitions(r.definitions),
        (err) => notify(err instanceof ApiError ? err.message : "Could not load details.", "error"),
      ),
    [notify],
  );

  useEffect(() => {
    load();
  }, [load]);

  const act = async (action: () => Promise<unknown>, message: string) => {
    try {
      await action();
      await Promise.all([load(), reload()]);
      notify(message, "success");
      return true;
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Could not save.", "error");
      await load();
      return false;
    }
  };

  return (
    <Dialog title="Kinds of details" size="wide" onClose={onClose}>
      <form
        className="definition-create"
        onSubmit={async (event) => {
          event.preventDefault();
          if (await act(() => api.createDefinition(label.trim(), type), "Added.")) setLabel("");
        }}
      >
        <div className="field">
          <label htmlFor="def-label">New kind of detail</label>
          <input id="def-label" value={label} maxLength={60} placeholder="e.g. Nickname" onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="def-type">Type</label>
          <select id="def-type" value={type} onChange={(e) => setType(e.target.value as ValueType)}>
            {CUSTOM_VALUE_TYPES.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="button button--primary" disabled={!label.trim()}>
          Add
        </button>
      </form>

      {definitions === null ? (
        <p>Loading…</p>
      ) : (
        <table className="definitions">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Type</th>
              <th scope="col">Used by</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {definitions.map((d) => (
              <DefinitionRow key={`${d.id}-${d.revision}`} definition={d} act={act} />
            ))}
          </tbody>
        </table>
      )}
    </Dialog>
  );
}

function DefinitionRow({
  definition,
  act,
}: {
  definition: AttributeDefinition;
  act: (action: () => Promise<unknown>, message: string) => Promise<boolean>;
}) {
  const [label, setLabel] = useState(definition.label);
  const revision = definition.revision ?? 1;
  return (
    <tr>
      <td>
        <input
          aria-label={`Name of ${definition.label}`}
          value={label}
          maxLength={60}
          onChange={(e) => setLabel(e.target.value)}
          onBlur={() =>
            label.trim() &&
            label.trim() !== definition.label &&
            act(() => api.updateDefinition(definition.id, { expected_revision: revision, label: label.trim() }), "Renamed.")
          }
        />
      </td>
      <td>
        {definition.builtin ? (
          VALUE_TYPE_LABELS[definition.value_type]
        ) : (
          <select
            aria-label={`Type of ${definition.label}`}
            value={definition.value_type}
            onChange={(e) =>
              act(
                () => api.updateDefinition(definition.id, { expected_revision: revision, value_type: e.target.value as ValueType }),
                "Type changed.",
              )
            }
          >
            {CUSTOM_VALUE_TYPES.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        )}
      </td>
      <td>{definition.usage ?? 0}</td>
      <td>
        {!definition.builtin && (
          <button
            type="button"
            className="link-button link-button--danger"
            disabled={(definition.usage ?? 0) > 0}
            title={(definition.usage ?? 0) > 0 ? "Remove its values first" : undefined}
            onClick={() => act(() => api.deleteDefinition(definition.id), "Deleted.")}
          >
            Delete
          </button>
        )}
      </td>
    </tr>
  );
}
