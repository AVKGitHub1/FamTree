import { useId } from "react";

interface Props {
  /** null = not chosen yet (used when the choice must be explicit). */
  value: boolean | null;
  onChange: (isPublic: boolean) => void;
  label?: string;
  privateDisabledReason?: string;
  compact?: boolean;
}

/** Public/private choice for one value or relationship. */
export function VisibilityChoice({ value, onChange, label = "Visibility", privateDisabledReason, compact }: Props) {
  const name = useId();
  return (
    <fieldset className={`visibility${compact ? " visibility--compact" : ""}`}>
      <legend className={compact ? "sr-only" : undefined}>{label}</legend>
      <label className={value === false ? "is-checked" : undefined}>
        <input
          type="radio"
          name={name}
          checked={value === false}
          disabled={Boolean(privateDisabledReason)}
          onChange={() => onChange(false)}
        />
        <span>🔒 Private</span>
      </label>
      <label className={value === true ? "is-checked" : undefined}>
        <input type="radio" name={name} checked={value === true} onChange={() => onChange(true)} />
        <span>🌐 Public</span>
      </label>
      {privateDisabledReason && !compact && <small className="hint">{privateDisabledReason}</small>}
    </fieldset>
  );
}

export function VisibilityBadge({ isPublic }: { isPublic: boolean | undefined }) {
  if (isPublic === undefined) return null;
  return (
    <span className={`badge ${isPublic ? "badge--public" : "badge--private"}`}>
      {isPublic ? "Public" : "Private"}
    </span>
  );
}
