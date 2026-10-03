import { useCallback, useEffect, useMemo, useReducer } from "react";
import { ApiError } from "./api/client";
import { calculateRelation } from "./api/endpoints";
import { AdminDialog } from "./components/admin/AdminDialog";
import { AttributesDialog } from "./components/attributes/AttributesDialog";
import { SignInDialog } from "./components/auth/SignInDialog";
import { WelcomeScreen } from "./components/auth/WelcomeScreen";
import { ExportDialog } from "./components/export/ExportDialog";
import { Header } from "./components/Header";
import { AddDialog } from "./components/person/AddDialog";
import { DeleteDialog } from "./components/person/DeleteDialog";
import { PersonPanel } from "./components/person/PersonPanel";
import { RelationBanner, RelationResults } from "./components/relation/RelationFlow";
import { GenerationControls } from "./components/tree/GenerationControls";
import { Legend } from "./components/tree/Legend";
import { TreeView, type Occlusion } from "./components/tree/TreeView";
import type { MenuItem } from "./components/ui/Menu";
import { cardLines } from "./lib/attributes";
import { isFull, limitsFor, resolveWindow, visibleRange } from "./lib/generations";
import { useMediaQuery } from "./lib/useMediaQuery";
import { SessionProvider, useSession } from "./state/session";
import { ToastProvider } from "./state/toasts";
import { TreeProvider, useTree } from "./state/tree";
import { initialUi, uiReducer } from "./state/ui";

export function App() {
  return (
    <ToastProvider>
      <SessionProvider>
        <TreeProvider>
          <Shell />
        </TreeProvider>
      </SessionProvider>
    </ToastProvider>
  );
}

const PANEL_WIDTH = 380;
const CONTROLS_WIDTH = 64; // generation controls column (wide screens)
const CONTROLS_ROW_HEIGHT = 104; // zoom + generation rows (small screens)

function Shell() {
  const { session, error: sessionError, can, askForCode } = useSession();
  const { status, index, error, reload } = useTree();
  const [ui, dispatch] = useReducer(uiReducer, initialUi);
  const small = useMediaQuery("(max-width: 720px)");

  // Drop references to people who are no longer visible (deleted, or signed out).
  useEffect(() => {
    if (index && ui.selectedId && !index.people.has(ui.selectedId)) dispatch({ type: "forget", id: ui.selectedId });
    if (index && ui.relation.stage === "result") {
      const { first, second } = ui.relation;
      if (!index.people.has(first) || !index.people.has(second)) dispatch({ type: "relationCancel" });
    }
  }, [index, ui.selectedId, ui.relation]);

  // --- generation window ---------------------------------------------------
  const selectedRow = ui.selectedId && index ? (index.rowOf.get(ui.selectedId) ?? null) : null;
  const limits = selectedRow != null && index ? limitsFor(selectedRow, index.maxRow) : null;
  const genWindow = limits ? resolveWindow(ui.window, limits) : null;
  const shown = index && genWindow && selectedRow != null ? visibleRange(selectedRow, genWindow, index.maxRow) : null;
  const lo = shown?.lo ?? 0;
  const hi = shown?.hi ?? index?.maxRow ?? 0;
  const range = useMemo(() => ({ lo, hi }), [lo, hi]);

  // --- relation flow ---------------------------------------------------------
  const relation = ui.relation;
  useEffect(() => {
    if (relation.stage !== "result" || relation.outcome || relation.error) return;
    let cancelled = false;
    calculateRelation(relation.first, relation.second).then(
      (outcome) => !cancelled && dispatch({ type: "relationResult", outcome, error: null }),
      (err) =>
        !cancelled &&
        dispatch({
          type: "relationResult",
          outcome: null,
          error: err instanceof ApiError ? err.message : "Could not calculate the relation.",
        }),
    );
    return () => {
      cancelled = true;
    };
  }, [relation]);

  useEffect(() => {
    if (relation.stage !== "pick") return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && dispatch({ type: "relationCancel" });
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [relation.stage]);

  const highlight = useMemo(() => {
    const people = new Set<string>();
    const links = new Set<string>();
    if (relation.stage === "result" && relation.outcome?.results[relation.active]) {
      for (const step of relation.outcome.results[relation.active].path) {
        people.add(step.person_id);
        if (step.link_id) links.add(step.link_id);
      }
    }
    return { people, links };
  }, [relation]);

  const picks = {
    first: relation.stage === "idle" ? null : relation.first,
    second: relation.stage === "result" ? relation.second : null,
  };

  // --- cards -----------------------------------------------------------------
  const onActivate = useCallback(
    (id: string) => {
      if (relation.stage === "pick") dispatch({ type: "relationPick", id });
      else dispatch({ type: "select", id, openDetails: true });
    },
    [relation.stage],
  );

  const menuFor = useCallback(
    (id: string): MenuItem[] => {
      const items: MenuItem[] = [{ label: "View details", onSelect: () => dispatch({ type: "select", id, openDetails: true }) }];
      if (can("add_connection")) {
        items.push({
          label: "Add connection",
          hint: "parent, child or spouse",
          onSelect: () => dispatch({ type: "openDialog", dialog: { kind: "add", anchorId: id } }),
        });
      }
      if (can("calculate_relation")) {
        items.push({
          label: "Calculate relation with another card",
          onSelect: () => dispatch({ type: "relationStart", first: id }),
        });
      }
      return items;
    },
    [can],
  );

  const describe = useCallback(
    (id: string) => {
      if (!index) return "";
      const person = index.people.get(id);
      if (!person) return "";
      const parts = [person.name, ...cardLines(person, index.definitions)];
      if (relation.stage === "pick") parts.push(relation.first ? "Press Enter to choose as the second person" : "Press Enter to choose as the first person");
      return parts.join(", ");
    },
    [index, relation],
  );

  const panelOpen = (ui.detailsOpen && ui.selectedId != null) || relation.stage === "result";
  const occlusion: Occlusion = useMemo(
    () => ({
      top: small ? CONTROLS_ROW_HEIGHT : 0,
      left: small ? 0 : CONTROLS_WIDTH,
      right: panelOpen && !small ? PANEL_WIDTH : 0,
      bottom: panelOpen && small ? Math.round(window.innerHeight * 0.5) : 0,
    }),
    [panelOpen, small],
  );

  // --- render ------------------------------------------------------------------
  if (sessionError && !session) {
    return (
      <FullPageMessage
        title="The family tree is unavailable"
        text={sessionError.status === 503 ? "The server is running but its storage is not ready. The site operator can find the reason in the server logs." : sessionError.message}
      />
    );
  }
  if (askForCode) return <WelcomeScreen />;

  const hasPeople = Boolean(index && index.people.size > 0);
  const selectedPerson = ui.selectedId ? index?.people.get(ui.selectedId) : undefined;
  const openAdd = () => dispatch({ type: "openDialog", dialog: { kind: "add", anchorId: null } });

  let main: React.ReactNode;
  if (!index) {
    main =
      status === "error" ? (
        <StateMessage title="Could not load the tree" text={error?.message ?? ""}>
          <button type="button" className="button button--primary" onClick={() => void reload()}>
            Try again
          </button>
        </StateMessage>
      ) : (
        <StateMessage title="Loading the family tree…" busy />
      );
  } else if (!hasPeople) {
    main = can("add_connection") ? (
      <StateMessage title="This family tree is empty" text="Start it by adding the first person.">
        <button type="button" className="button button--primary" onClick={openAdd}>
          Add the first person
        </button>
      </StateMessage>
    ) : (
      <StateMessage
        title="Nothing to show yet"
        text={session?.authenticated ? "Nobody has been added to the tree yet." : "There is nothing public in this tree yet. If you have an access code, sign in."}
      />
    );
  } else {
    main = (
      <>
        <TreeView
          index={index}
          range={range}
          selectedId={ui.selectedId}
          picks={picks}
          highlight={highlight}
          occlusion={occlusion}
          fitRequest={ui.fitRequest}
          focusScale={small ? 0.75 : null}
          menuFor={menuFor}
          onActivate={onActivate}
          onBackground={() => relation.stage !== "pick" && dispatch({ type: "deselect" })}
          describe={describe}
        />
        <GenerationControls
          window={genWindow}
          limits={limits}
          onChange={(next) => dispatch({ type: "setWindow", window: next })}
          onReset={() => dispatch({ type: "setWindow", window: null })}
        />
        {status === "error" && error && (
          <div className="error-banner floating" role="alert">
            {error.message}{" "}
            <button type="button" className="link-button" onClick={() => void reload()}>
              Retry
            </button>
          </div>
        )}
      </>
    );
  }

  return (
    <div className={`app${panelOpen ? " has-panel" : ""}`}>
      <Header
        hasPeople={hasPeople}
        relationActive={relation.stage !== "idle"}
        onRelation={() => dispatch(relation.stage === "idle" ? { type: "relationStart" } : { type: "relationCancel" })}
        onAdd={openAdd}
        onExport={() => dispatch({ type: "openDialog", dialog: { kind: "export" } })}
        onAttributes={() => dispatch({ type: "openDialog", dialog: { kind: "attributes" } })}
        onAdmin={() => dispatch({ type: "openDialog", dialog: { kind: "admin" } })}
        onSignIn={() => dispatch({ type: "openDialog", dialog: { kind: "signin" } })}
        onLegend={() => dispatch({ type: "toggleLegend" })}
      />
      {relation.stage === "pick" && (
        <RelationBanner
          firstName={relation.first ? (index?.people.get(relation.first)?.name ?? null) : null}
          onCancel={() => dispatch({ type: "relationCancel" })}
        />
      )}
      <main className="main">
        {main}
        {ui.legendOpen && <Legend onClose={() => dispatch({ type: "toggleLegend" })} />}
      </main>

      {index && relation.stage === "result" ? (
        <RelationResults
          outcome={relation.outcome}
          error={relation.error}
          active={relation.active}
          onActivate={(i) => dispatch({ type: "relationActive", index: i })}
          onSwap={() => dispatch({ type: "relationSwap" })}
          onAgain={() => dispatch({ type: "relationStart" })}
          onClose={() => dispatch({ type: "relationCancel" })}
        />
      ) : (
        index &&
        ui.detailsOpen &&
        selectedPerson && (
          <PersonPanel
            key={selectedPerson.id}
            index={index}
            person={selectedPerson}
            canEdit={can("edit_person")}
            onSelect={(id) => dispatch({ type: "select", id, openDetails: true })}
            onAddConnection={(id) => dispatch({ type: "openDialog", dialog: { kind: "add", anchorId: id } })}
            onRelation={(id) => dispatch({ type: "relationStart", first: id })}
            onDelete={(id) => dispatch({ type: "openDialog", dialog: { kind: "delete", personId: id } })}
            onClose={() => dispatch({ type: "closeDetails" })}
          />
        )
      )}

      {ui.dialog?.kind === "signin" && <SignInDialog onClose={() => dispatch({ type: "closeDialog" })} />}
      {ui.dialog?.kind === "add" && index && (
        <AddDialog
          index={index}
          anchorId={ui.dialog.anchorId}
          onClose={() => dispatch({ type: "closeDialog" })}
          onCreated={(id) => dispatch({ type: "select", id, openDetails: true })}
        />
      )}
      {ui.dialog?.kind === "delete" && index && (
        <DeleteDialog
          index={index}
          personId={ui.dialog.personId}
          onClose={() => dispatch({ type: "closeDialog" })}
          onDeleted={() => {
            dispatch({ type: "closeDialog" });
            dispatch({ type: "deselect" });
          }}
        />
      )}
      {ui.dialog?.kind === "export" && index && (
        <ExportDialog
          index={index}
          view={
            ui.selectedId && genWindow && limits
              ? { selectedId: ui.selectedId, window: genWindow, filtered: !isFull(genWindow, limits) }
              : null
          }
          onClose={() => dispatch({ type: "closeDialog" })}
        />
      )}
      {ui.dialog?.kind === "admin" && <AdminDialog onClose={() => dispatch({ type: "closeDialog" })} />}
      {ui.dialog?.kind === "attributes" && <AttributesDialog onClose={() => dispatch({ type: "closeDialog" })} />}
    </div>
  );
}

function StateMessage({ title, text, busy, children }: { title: string; text?: string; busy?: boolean; children?: React.ReactNode }) {
  return (
    <div className="state-message" role={busy ? "status" : undefined}>
      {busy && <div className="spinner" aria-hidden="true" />}
      <h2>{title}</h2>
      {text && <p>{text}</p>}
      {children}
    </div>
  );
}

function FullPageMessage({ title, text }: { title: string; text: string }) {
  return (
    <div className="app">
      <header className="header">
        <h1 className="header__title">FamTree</h1>
      </header>
      <main className="main">
        <StateMessage title={title} text={text}>
          <button type="button" className="button" onClick={() => location.reload()}>
            Reload
          </button>
        </StateMessage>
      </main>
    </div>
  );
}
