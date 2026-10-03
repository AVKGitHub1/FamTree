/** What each kind of line means; shapes differ, not just colours. */
export function Legend({ onClose }: { onClose: () => void }) {
  return (
    <aside className="legend" aria-label="Legend">
      <div className="legend__header">
        <strong>Legend</strong>
        <button type="button" className="icon-button" aria-label="Close legend" onClick={onClose}>
          ×
        </button>
      </div>
      <ul>
        <li>
          <svg width="40" height="12" aria-hidden="true" className="connector connector--spouse">
            <path className="line-outer" d="M2 6 L38 6" />
            <path className="line-inner" d="M2 6 L38 6" />
          </svg>
          Spouses (double line)
        </li>
        <li>
          <svg width="40" height="12" aria-hidden="true" className="connector connector--family">
            <path className="line" d="M2 6 L38 6" />
          </svg>
          Parent and child
        </li>
        <li>
          <svg width="40" height="16" aria-hidden="true" className="connector connector--family">
            <g className="junction">
              <rect x="2" y="2" width="36" height="12" rx="4" />
            </g>
          </svg>
          Joins parents to their shared children
        </li>
        <li>
          <svg width="40" height="12" aria-hidden="true" className="connector connector--family">
            <path className="line" d="M2 6 L38 6 M20 6 L20 12" />
            <circle className="dot" cx="20" cy="6" r="3" />
          </svg>
          Dot: lines branch here
        </li>
        <li>
          <svg width="40" height="14" aria-hidden="true" className="connector connector--family">
            <path className="line" d="M2 7 L15 7 M25 7 L38 7 M20 0 L20 14" />
          </svg>
          Gap: lines cross without connecting
        </li>
        <li>
          <svg width="40" height="16" aria-hidden="true" className="continuation">
            <path className="stub" d="M20 16 L20 2" />
            <path className="stub-arrow" d="M16 8 L20 2 L24 8" />
          </svg>
          Relatives who are not shown
        </li>
      </ul>
      <p className="legend__hint">
        Drag over cards to select them; Ctrl+click (⌘+click on a Mac) adds or removes one. To move the tree, hold
        Space and drag, drag with the middle mouse button, or use the arrow keys. On a touch screen, drag to move.
      </p>
    </aside>
  );
}
