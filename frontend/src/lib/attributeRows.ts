import { pictureUrl } from "../api/endpoints";
import type { AttributeDefinition, AttributeInput, ImageValue, NewDefinition, Person, ValueType } from "../api/types";
import { draftFrom, parseDraft, type Draft } from "./drafts";

/** One attribute being edited: an existing definition or one created here. */
export interface AttributeRow {
  key: string;
  definition: { id: string } | { ref: string; label: string; value_type: ValueType };
  draft: Draft;
  isPublic: boolean;
}

let counter = 0;
export const localKey = (prefix = "k") => `${prefix}${++counter}`;

export function rowsFromPerson(person: Person, definitions: Map<string, AttributeDefinition>): AttributeRow[] {
  return person.attributes.flatMap((attr) => {
    const def = definitions.get(attr.definition_id);
    if (!def) return [];
    return [
      {
        key: localKey(),
        definition: { id: def.id },
        draft: draftFrom(
          def.value_type,
          attr.value,
          def.value_type === "image" ? pictureUrl(person.id, (attr.value as ImageValue).id, "thumb") : null,
        ),
        isPublic: attr.is_public ?? false,
      },
    ];
  });
}

export function rowLabel(row: AttributeRow, definitions: Map<string, AttributeDefinition>): string {
  return "id" in row.definition ? definitions.get(row.definition.id)?.label ?? "Attribute" : row.definition.label;
}

export interface RowsPayload {
  attributes: AttributeInput[];
  definitions: NewDefinition[];
  errors: string[];
}

/** Validate rows and build the API payload. Empty values are simply dropped. */
export function rowsToPayload(rows: AttributeRow[], definitions: Map<string, AttributeDefinition>): RowsPayload {
  const payload: RowsPayload = { attributes: [], definitions: [], errors: [] };
  for (const row of rows) {
    const parsed = parseDraft(row.draft);
    const label = rowLabel(row, definitions);
    if (!parsed.ok) {
      payload.errors.push(`${label}: ${parsed.error}`);
      continue;
    }
    if (parsed.value == null) continue;
    if ("ref" in row.definition) {
      payload.definitions.push({ ref: row.definition.ref, label: row.definition.label, value_type: row.definition.value_type });
      payload.attributes.push({ definition: { ref: row.definition.ref }, value: parsed.value, is_public: row.isPublic });
    } else {
      payload.attributes.push({ definition: { id: row.definition.id }, value: parsed.value, is_public: row.isPublic });
    }
  }
  return payload;
}
