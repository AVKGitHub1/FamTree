import { applyStep, canStep, isFull, type GenerationWindow, type Limits, type Step } from "../../lib/generations";

interface Props {
  window: GenerationWindow | null; // resolved window, or null with no selection
  limits: Limits | null;
  onChange: (window: GenerationWindow) => void;
  onReset: () => void;
}

const BUTTONS: { step: Step; text: string; label: string }[] = [
  { step: "moreAbove", text: "^+", label: "Show one more generation above" },
  { step: "fewerAbove", text: "^-", label: "Hide one generation above" },
  { step: "moreBelow", text: "⌄+", label: "Show one more generation below" },
  { step: "fewerBelow", text: "⌄-", label: "Hide one generation below" },
];

export function GenerationControls({ window, limits, onChange, onReset }: Props) {
  const active = window && limits;
  return (
    <div className="generation-controls" role="group" aria-label="Generations shown">
      {BUTTONS.map(({ step, text, label }) => (
        <button
          key={step}
          type="button"
          className="control-button"
          aria-label={label}
          title={active ? label : `${label} (select a person first)`}
          disabled={!active || !canStep(window, limits, step)}
          onClick={() => active && onChange(applyStep(window, limits, step))}
        >
          {text}
        </button>
      ))}
      <button
        type="button"
        className="control-button control-button--text"
        aria-label="Show the full tree"
        title="Show the full tree"
        disabled={!active || isFull(window, limits)}
        onClick={onReset}
      >
        All
      </button>
      {active && (
        <span className="generation-controls__status" aria-live="polite">
          ↑{window.above}/{limits.maxAbove} ↓{window.below}/{limits.maxBelow}
        </span>
      )}
    </div>
  );
}
