import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { searchPeople } from "../../api/endpoints";
import type { SearchHit } from "../../api/types";

export type Picked = { kind: "existing"; id: string; name: string } | { kind: "new"; name: string };

interface Props {
  label: string;
  value: Picked | null;
  onChange: (value: Picked | null) => void;
  exclude?: string[];
  allowNew?: boolean;
  autoFocus?: boolean;
}

/** Combobox: matching names (with context to tell namesakes apart) from the
 * server's authorized search, plus an explicit "create new person" choice.
 * Choosing a match links that person; nothing is created implicitly. */
export function PersonPicker({ label, value, onChange, exclude = [], allowNew = true, autoFocus }: Props) {
  const [text, setText] = useState(value?.name ?? "");
  const [found, setFound] = useState<{ query: string; hits: SearchHit[] }>({ query: "", hits: [] });
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const inputId = useId();
  const excludeKey = exclude.join(",");
  const latest = useRef(0);

  const query = text.trim();
  // Results can be chosen only for the query they answer. While a newer
  // search runs, the last answer stays in view, dimmed and not choosable, so
  // the list does not empty and refill with every keystroke.
  const loading = Boolean(query) && found.query !== query;
  const results = loading ? [] : found.hits;
  const stale = loading ? found.hits : [];

  useEffect(() => {
    if (!query) return;
    const mine = ++latest.current;
    const timer = window.setTimeout(() => {
      searchPeople(query, excludeKey ? excludeKey.split(",") : []).then(
        (r) => mine === latest.current && setFound({ query, hits: r.results }),
        () => mine === latest.current && setFound({ query, hits: [] }),
      );
    }, 180);
    return () => window.clearTimeout(timer);
  }, [query, excludeKey]);

  // "Create new" is offered only once the search has answered, so a quick
  // Enter never creates a duplicate of someone who was about to be listed.
  const offerNew = allowNew && Boolean(query) && !loading;
  const options: Picked[] = [
    ...results.map((hit): Picked => ({ kind: "existing", id: hit.id, name: hit.name })),
    ...(offerNew ? [{ kind: "new", name: query } as Picked] : []),
  ];

  const choose = (option: Picked) => {
    onChange(option);
    setText(option.name);
    setOpen(false);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, options.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter" && open && options[active]) {
      event.preventDefault();
      choose(options[active]);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
    }
  };

  const optionId = (i: number) => `${listId}-${i}`;
  return (
    <div className="picker">
      <label htmlFor={inputId}>{label}</label>
      <input
        id={inputId}
        type="text"
        role="combobox"
        autoComplete="off"
        autoFocus={autoFocus}
        aria-expanded={open && options.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && options[active] ? optionId(active) : undefined}
        value={text}
        placeholder="Start typing a name…"
        onChange={(event) => {
          setText(event.target.value);
          setActive(0);
          setOpen(true);
          if (value) onChange(null);
        }}
        onFocus={() => text && setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
      />
      {value && (
        <p className="picker__chosen">
          {value.kind === "existing" ? (
            <>Linking to the existing person <strong>{value.name}</strong>.</>
          ) : (
            <>A new person named <strong>{value.name}</strong> will be created.</>
          )}
        </p>
      )}
      {open && query && !(value && value.name === text) && (
        <ul id={listId} role="listbox" className="picker__list" aria-label={`${label} suggestions`}>
          {results.map((hit, i) => (
            <li
              key={hit.id}
              id={optionId(i)}
              role="option"
              aria-selected={i === active}
              className={i === active ? "is-active" : undefined}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(options[i])}
            >
              <span className="picker__name">{hit.name}</span>
              {hit.context.length > 0 && <span className="picker__context">{hit.context.join(" · ")}</span>}
            </li>
          ))}
          {stale.map((hit) => (
            <li key={hit.id} className="is-stale" aria-hidden="true">
              <span className="picker__name">{hit.name}</span>
              {hit.context.length > 0 && <span className="picker__context">{hit.context.join(" · ")}</span>}
            </li>
          ))}
          {loading && (
            <li className="picker__empty" role="presentation">
              Searching…
            </li>
          )}
          {!loading && results.length === 0 && (
            <li className="picker__empty" role="presentation">
              No matching people.
            </li>
          )}
          {offerNew && (
            <li
              id={optionId(results.length)}
              role="option"
              aria-selected={active === results.length}
              className={`picker__new${active === results.length ? " is-active" : ""}`}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(options[results.length])}
            >
              + Create a new person named “{text.trim()}”
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
