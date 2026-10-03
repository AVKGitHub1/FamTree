import { memo, type KeyboardEvent } from "react";
import type { LayoutNode, Person } from "../../api/types";
import { Menu, type MenuItem } from "../ui/Menu";

interface Props {
  person: Person;
  node: LayoutNode;
  lines: string[];
  selected: boolean;
  pick: 1 | 2 | null;
  onPath: boolean;
  menuItems: MenuItem[] | null;
  description: string;
  onActivate: (id: string) => void;
  onNavigate: (id: string, key: string) => void;
  registerRef: (id: string, element: HTMLDivElement | null) => void;
}

export const PersonCard = memo(function PersonCard({
  person,
  node,
  lines,
  selected,
  pick,
  onPath,
  menuItems,
  description,
  onActivate,
  onNavigate,
  registerRef,
}: Props) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onActivate(person.id);
    } else if (event.key.startsWith("Arrow")) {
      event.preventDefault();
      onNavigate(person.id, event.key);
    }
  };
  const classes = [
    "card",
    selected && "is-selected",
    pick && `is-pick-${pick}`,
    onPath && "is-on-path",
  ].filter(Boolean);

  return (
    <div
      ref={(el) => registerRef(person.id, el)}
      className={classes.join(" ")}
      style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={description}
      data-person-id={person.id}
      onClick={(event) => {
        event.stopPropagation();
        onActivate(person.id);
      }}
      onKeyDown={onKeyDown}
    >
      {pick && (
        <span className="card__pick" aria-hidden="true">
          {pick}
        </span>
      )}
      <div className="card__name">{person.name}</div>
      {lines.map((line) => (
        <div key={line} className="card__line">
          {line}
        </div>
      ))}
      {menuItems && (
        <Menu label={`Actions for ${person.name}`} items={menuItems} buttonContent="⋮" className="card__menu" />
      )}
    </div>
  );
});
