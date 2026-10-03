import { memo, type KeyboardEvent } from "react";
import type { LayoutNode, Person } from "../../api/types";
import { Menu, type MenuItem } from "../ui/Menu";

interface Props {
  person: Person;
  node: LayoutNode;
  lines: string[];
  /** URL of the card-sized profile picture. */
  picture: string | null;
  selected: boolean;
  /** In the selection (View Only Selected). */
  marked: boolean;
  pick: 1 | 2 | null;
  onPath: boolean;
  menuItems: MenuItem[] | null;
  description: string;
  onActivate: (id: string) => void;
  /** Ctrl/⌘ + click or Enter: add to or remove from the selection. */
  onToggle: (id: string) => void;
  onNavigate: (id: string, key: string) => void;
  registerRef: (id: string, element: HTMLDivElement | null) => void;
}

export const PersonCard = memo(function PersonCard({
  person,
  node,
  lines,
  picture,
  selected,
  marked,
  pick,
  onPath,
  menuItems,
  description,
  onActivate,
  onToggle,
  onNavigate,
  registerRef,
}: Props) {
  const activate = (event: { ctrlKey: boolean; metaKey: boolean }) =>
    event.ctrlKey || event.metaKey ? onToggle(person.id) : onActivate(person.id);
  // Space, which doubles as the pan key, is handled by the tree view.
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter") {
      event.preventDefault();
      activate(event);
    } else if (event.key.startsWith("Arrow")) {
      event.preventDefault();
      onNavigate(person.id, event.key);
    }
  };
  const classes = [
    "card",
    picture && "has-picture",
    selected && "is-selected",
    marked && "is-marked",
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
        activate(event);
      }}
      onKeyDown={onKeyDown}
    >
      {pick && (
        <span className="card__pick" aria-hidden="true">
          {pick}
        </span>
      )}
      {picture && <img className="avatar card__avatar" src={picture} alt="" loading="lazy" decoding="async" draggable={false} />}
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
