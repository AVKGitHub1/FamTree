import type { AttributeDefinition, AttributeValue, PartialDate, Person, ValueType } from "../api/types";
import { formatPartialDate } from "./dates";

export const BIRTH_DATE = "birth_date";
export const LOCATION = "location";
export const PROFESSION = "profession";
export const DESCRIPTION = "description";

export const VALUE_TYPE_LABELS: Record<ValueType, string> = {
  text: "Short text",
  long_text: "Long text",
  date: "Date",
  number: "Number",
  url: "Link",
};

export function displayValue(type: ValueType, value: AttributeValue): string {
  if (type === "date") return formatPartialDate(value as PartialDate);
  return String(value);
}

export function attributeOf(person: Person, definitionId: string) {
  return person.attributes.find((a) => a.definition_id === definitionId);
}

/** The short lines shown on a tree card (only data the caller received). */
export function cardLines(person: Person, definitions: Map<string, AttributeDefinition>): string[] {
  const lines: string[] = [];
  const birth = attributeOf(person, BIRTH_DATE);
  if (birth && definitions.has(BIRTH_DATE)) lines.push(`b. ${formatPartialDate(birth.value as PartialDate)}`);
  for (const id of [PROFESSION, LOCATION]) {
    const attr = attributeOf(person, id);
    const def = definitions.get(id);
    if (attr && def) {
      lines.push(displayValue(def.value_type, attr.value));
      break;
    }
  }
  return lines;
}
