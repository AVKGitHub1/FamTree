import { ROLE_LABELS, useSession } from "../state/session";
import { THEME_LABELS, useTheme, type ThemeChoice } from "../state/theme";

interface Props {
  hasPeople: boolean;
  relationActive: boolean;
  onRelation: () => void;
  selectedCount: number;
  viewingSelected: boolean;
  onViewSelected: () => void;
  onDefaultView: () => void;
  onAdd: () => void;
  onExport: () => void;
  onAttributes: () => void;
  onAdmin: () => void;
  onSignIn: () => void;
  onLegend: () => void;
}

export function Header(props: Props) {
  const { session, can, signOut } = useSession();
  const [theme, setTheme] = useTheme();
  const role = session?.role ?? "guest";
  return (
    <header className="header">
      <h1 className="header__title">FamTree</h1>
      <nav className="header__actions" aria-label="Main">
        <button
          type="button"
          className="button button--primary"
          onClick={props.onRelation}
          disabled={!props.hasPeople || !can("calculate_relation")}
          aria-pressed={props.relationActive}
        >
          Calculate Relation
        </button>
        <button
          type="button"
          className={`button${props.viewingSelected ? " is-active" : ""}`}
          onClick={props.onViewSelected}
          disabled={!props.hasPeople || props.selectedCount === 0}
          title={
            props.selectedCount
              ? `Show only the ${props.selectedCount} selected ${props.selectedCount === 1 ? "person" : "people"}`
              : "Drag over cards, or Ctrl+click them, to select people first"
          }
        >
          View Only Selected
          {props.selectedCount > 0 && <span className="button__count">{props.selectedCount}</span>}
        </button>
        <button
          type="button"
          className="button"
          onClick={props.onDefaultView}
          disabled={!props.hasPeople}
          title="Show the full tree, fitted to the screen"
        >
          Default View
        </button>
        {can("add_connection") && (
          <button type="button" className="button" onClick={props.onAdd}>
            {props.hasPeople ? "Add person" : "Add first person"}
          </button>
        )}
        {can("export") && (
          <button type="button" className="button" onClick={props.onExport} disabled={!props.hasPeople}>
            Export
          </button>
        )}
        <button type="button" className="button" onClick={props.onLegend}>
          Legend
        </button>
        {can("manage_attributes") && (
          <button type="button" className="button" onClick={props.onAttributes}>
            Details
          </button>
        )}
        {can("manage_access") && (
          <button type="button" className="button" onClick={props.onAdmin}>
            Admin
          </button>
        )}
        <label className="sr-only" htmlFor="theme-select">
          Colour theme
        </label>
        <select
          id="theme-select"
          className="theme-select"
          value={theme}
          title="Colour theme"
          onChange={(e) => setTheme(e.target.value as ThemeChoice)}
        >
          {Object.entries(THEME_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label} theme
            </option>
          ))}
        </select>
        <span className="role-badge" title="Your access">
          {ROLE_LABELS[role]}
        </span>
        {session?.authenticated ? (
          <button type="button" className="button" onClick={() => void signOut()}>
            Sign out
          </button>
        ) : (
          <button type="button" className="button" onClick={props.onSignIn}>
            Sign in
          </button>
        )}
      </nav>
    </header>
  );
}
