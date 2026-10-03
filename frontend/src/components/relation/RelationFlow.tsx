import { useState } from "react";
import type { RelationOutcome, RelationResult } from "../../api/types";

interface BannerProps {
  firstName: string | null;
  onCancel: () => void;
}

/** Prompts during the two-person selection. Escape also cancels. */
export function RelationBanner({ firstName, onCancel }: BannerProps) {
  return (
    <div className="relation-banner" role="status" aria-live="polite">
      <span className="relation-banner__step">{firstName ? "2" : "1"}</span>
      <span>
        {firstName ? (
          <>
            First person: <strong>{firstName}</strong>. Now select the <strong>second</strong> person.
          </>
        ) : (
          <>
            Select the <strong>first</strong> person (click a card, or focus it and press Enter).
          </>
        )}
      </span>
      <button type="button" className="button" onClick={onCancel}>
        Cancel
      </button>
    </div>
  );
}

interface ResultsProps {
  outcome: RelationOutcome | null;
  error: string | null;
  active: number;
  onActivate: (index: number) => void;
  onAgain: () => void;
  onClose: () => void;
  onSwap: () => void;
}

const STEP_WORDS: Record<string, string> = { parent: "parent", child: "child", spouse: "spouse" };

function PathText({ result }: { result: RelationResult }) {
  return (
    <ol className="relation-path">
      {result.path.map((step, i) => (
        <li key={`${step.person_id}-${i}`}>
          {i > 0 && <span className="relation-path__via">{STEP_WORDS[step.step]} →</span>} {step.name}
        </li>
      ))}
    </ol>
  );
}

/** The most familiar name first, then the other ways of saying it. */
function MarathiNames({ names }: { names: string[] }) {
  if (names.length === 0) return <span className="relation-marathi muted">No Marathi relationship name found.</span>;
  const [first, ...others] = names;
  return (
    <span className="relation-marathi">
      <span lang="mr" className="relation-marathi__name">
        {first}
      </span>
      {others.length > 0 && (
        <span className="hint">
          Also <span lang="mr">{others.join(", ")}</span>
        </span>
      )}
    </span>
  );
}

export function RelationResults({ outcome, error, active, onActivate, onAgain, onClose, onSwap }: ResultsProps) {
  const [marathi, setMarathi] = useState(false);
  const found = outcome != null && outcome.results.length > 0;
  return (
    <aside className="panel relation-results" aria-label="Relation result">
      <div className="panel__header">
        <h2>Relation</h2>
        <button type="button" className="icon-button" aria-label="Close relation result" onClick={onClose}>
          ×
        </button>
      </div>
      {!outcome && !error && <p>Calculating…</p>}
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {outcome && outcome.results.length === 0 && <p className="relation-none">{outcome.message}</p>}
      {found && (
        <>
          {outcome.results.length > 1 && (
            <p className="hint">
              {outcome.results.length} distinct relationships were found. Choose one to see its path on the tree.
            </p>
          )}
          <ul className="relation-list">
            {outcome.results.map((result, i) => (
              <li key={`${result.kind}-${i}`} className={i === active ? "is-active" : undefined}>
                <button type="button" className="relation-result" aria-pressed={i === active} onClick={() => onActivate(i)}>
                  <strong>{result.statement}</strong>
                  {result.common_ancestors.length > 0 && (
                    <span className="muted">
                      Through {result.common_ancestors.map((a) => a.name).join(" and ")}
                    </span>
                  )}
                  {marathi && <MarathiNames names={result.marathi} />}
                </button>
                {i === active && <PathText result={result} />}
              </li>
            ))}
          </ul>
        </>
      )}
      <div className="panel__actions">
        {found && (
          <button
            type="button"
            className={marathi ? "button is-active" : "button"}
            lang="mr"
            title="Show the relationship in Marathi"
            aria-pressed={marathi}
            onClick={() => setMarathi(!marathi)}
          >
            मराठीत नातं
          </button>
        )}
        <button type="button" className="button" onClick={onSwap} disabled={!outcome}>
          Swap order
        </button>
        <button type="button" className="button" onClick={onAgain}>
          Choose two other people
        </button>
      </div>
    </aside>
  );
}
