import type {
  AttributeDefinition,
  AttributeValue,
  Gender,
  ImageValue,
  ParentRole,
  PartialDate,
  Person,
  ValueType,
} from "../api/types";
import { formatPartialDate } from "./dates";

export const BIRTH_DATE = "birth_date";
export const LOCATION = "location";
export const PROFESSION = "profession";
export const DESCRIPTION = "description";
export const PROFILE_PIC = "profile_pic";
export const GENDER = "gender";

export const GENDER_LABELS: Record<Gender, string> = { female: "Female", male: "Male", other: "Other" };

export const VALUE_TYPE_LABELS: Record<ValueType, string> = {
  text: "Short text",
  long_text: "Long text",
  date: "Date",
  number: "Number",
  url: "Link",
  image: "Picture",
  gender: "Female, male or other",
};

/** Types editors may give their own attributes: pictures are kept only in the
 * built-in Profile Pic, and gender in the built-in Gender. */
export const CUSTOM_VALUE_TYPES = Object.entries(VALUE_TYPE_LABELS).filter(
  ([type]) => type !== "image" && type !== "gender",
) as [ValueType, string][];

export function displayValue(type: ValueType, value: AttributeValue): string {
  if (type === "date") return formatPartialDate(value as PartialDate);
  if (type === "image") return "Picture";
  if (type === "gender") return GENDER_LABELS[value as Gender] ?? String(value);
  return String(value);
}

/** Mother for a recorded female, father for a male; null otherwise. Only a
 * suggestion: the role belongs to each parent link and editors choose it. */
export function roleForGender(gender: string | null | undefined): ParentRole | null {
  return gender === "female" ? "mother" : gender === "male" ? "father" : null;
}

/** The person's recorded gender, if the caller received it. */
export function genderOf(person: Person, definitions: Map<string, AttributeDefinition>): Gender | null {
  const attr = attributeOf(person, GENDER);
  return attr && definitions.get(GENDER)?.value_type === "gender" ? (attr.value as Gender) : null;
}

/** The person's profile picture, if the caller received one. */
export function profilePicture(person: Person, definitions: Map<string, AttributeDefinition>): ImageValue | null {
  const attr = attributeOf(person, PROFILE_PIC);
  return attr && definitions.get(PROFILE_PIC)?.value_type === "image" ? (attr.value as ImageValue) : null;
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
