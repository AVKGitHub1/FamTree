// Namesakes: people already in the tree with the name someone is being given.

import type { Person } from "../api/types";
import { cardLines } from "./attributes";
import { nameOf, type TreeIndex } from "./treeIndex";

/** Comparison form of a name: case, accents and spacing are ignored, as in
 * the server's name search. */
export function nameKey(name: string): string {
  return name.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ").trim();
}

export interface Namesake {
  person: Person;
  /** Facts that tell same-named people apart. */
  context: string[];
}

/** People in the tree named `name`, other than those in `exclude`. */
export function namesakes(index: TreeIndex, name: string, exclude: readonly string[] = []): Namesake[] {
  const key = nameKey(name);
  if (!key) return [];
  return index.data.people
    .filter((person) => !exclude.includes(person.id) && nameKey(person.name) === key)
    .map((person) => {
      const parents = (index.parentsOf.get(person.id) ?? []).map((link) => nameOf(index, link.parent_id));
      const context = cardLines(person, index.definitions);
      if (parents.length) context.push(`child of ${parents.join(" & ")}`);
      return { person, context };
    });
}
