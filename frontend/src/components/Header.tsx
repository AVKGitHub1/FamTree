import { ROLE_LABELS, useSession } from "../state/session";
import { THEME_LABELS, useTheme, type ThemeChoice } from "../state/theme";

interface Props {
  hasPeople: boolean;
  relationActive: boolean;
  onRelation: () => void;
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
