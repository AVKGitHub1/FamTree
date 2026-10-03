import { useMemo } from "react";
import { namesakes } from "../../lib/namesakes";
import type { TreeIndex } from "../../lib/treeIndex";

interface Props {
  index: TreeIndex;
  name: string;
  /** People not to count, such as the one being renamed. */
  exclude?: readonly string[];
  /** What saving anyway does, and what to do instead. */
  advice: string;
}

/** Warns, without preventing it, that the tree already has someone of this name. */
export function NamesakeWarning({ index, name, exclude, advice }: Props) {
  const found = useMemo(() => namesakes(index, name, exclude), [index, name, exclude]);
  if (!found.length) return null;
  return (
    <div className="namesake" role="status">
      <p>
        <strong>{found.length === 1 ? "Someone" : `${found.length} people`}</strong> named “{found[0].person.name}”{" "}
        {found.length === 1 ? "is" : "are"} already in the tree:
      </p>
      <ul>
        {found.map(({ person, context }) => (
          <li key={person.id}>{context.length ? context.join(" · ") : "no details recorded"}</li>
        ))}
      </ul>
      <p className="hint">{advice}</p>
    </div>
  );
}
