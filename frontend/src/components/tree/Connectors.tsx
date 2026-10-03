import { memo } from "react";
import type { Connector, Crossing, Point } from "../../api/types";
import type { Continuations } from "../../lib/generations";
import type { TreeIndex } from "../../lib/treeIndex";

const pathData = (points: Point[]) =>
  points.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");

interface Props {
  index: TreeIndex;
  connectors: Connector[];
  crossings: Crossing[];
  continuations: Map<string, Continuations>;
  highlightLinks: Set<string>;
}

/** All lines, drawn beneath the cards. Line kinds differ in form (double vs.
 * single line, labelled junction box), not only in colour. */
export const Connectors = memo(function Connectors({
  index,
  connectors,
  crossings,
  continuations,
  highlightLinks,
}: Props) {
  const { layout } = index.data;
  const byId = new Map(connectors.map((c) => [c.id, c]));
  return (
    <svg
      className="connectors"
      width={layout.width}
      height={layout.height}
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      aria-hidden="true"
    >
      {connectors.map((c) => {
        const highlighted = c.links.some((id) => highlightLinks.has(id));
        return (
          <g key={c.id} className={`connector connector--${c.type}${highlighted ? " is-highlighted" : ""}`}>
            {c.paths.map((points, i) =>
              c.type === "spouse" ? (
                <g key={i}>
                  <path className="line-outer" d={pathData(points)} />
                  <path className="line-inner" d={pathData(points)} />
                </g>
              ) : (
                <path key={i} className="line" d={pathData(points)} />
              ),
            )}
          </g>
        );
      })}

      {/* Break the lower line at each crossing so it never reads as a junction. */}
      {crossings.map((x) => {
        const over = byId.get(x.over);
        const under = byId.get(x.under);
        if (!over || !under) return null;
        const thick = under.type === "spouse" ? 6 : 3.4;
        return (
          <g key={`${x.over}|${x.under}|${x.x}|${x.y}`} className={`crossing connector--${over.type}`}>
            <rect className="crossing__gap" x={x.x - 5} y={x.y - thick / 2} width={10} height={thick} />
            {over.type === "spouse" ? (
              <>
                <path className="line-outer" d={`M${x.x} ${x.y - 6} L${x.x} ${x.y + 6}`} />
                <path className="line-inner" d={`M${x.x} ${x.y - 6} L${x.x} ${x.y + 6}`} />
              </>
            ) : (
              <path className="line" d={`M${x.x} ${x.y - 6} L${x.x} ${x.y + 6}`} />
            )}
          </g>
        );
      })}

      {connectors.map((c) => (
        <g key={`m-${c.id}`} className="connector connector--family">
          {c.dots.map(([x, y]) => (
            <circle key={`${x},${y}`} className="dot" cx={x} cy={y} r={3.2} />
          ))}
          {c.junction && (
            <g className="junction">
              <rect
                x={c.junction.x - c.junction.width / 2}
                y={c.junction.y - c.junction.height / 2}
                width={c.junction.width}
                height={c.junction.height}
                rx={5}
              />
              <text x={c.junction.x} y={c.junction.y + 3.5} textAnchor="middle">
                parents
              </text>
            </g>
          )}
        </g>
      ))}

      {[...continuations].map(([id, marks]) => {
        const node = layout.nodes[id];
        if (!node) return null;
        const cx = node.x + node.width / 2;
        return (
          <g key={`c-${id}`} className="continuation">
            {marks.up && <Stub x={cx} y={node.y} dy={-16} />}
            {marks.down && <Stub x={cx} y={node.y + node.height} dy={16} />}
            {marks.side && <Stub x={node.x + node.width * 0.75} y={node.y + node.height} dy={16} />}
          </g>
        );
      })}
    </svg>
  );
});

/** Dashed line with an arrowhead: relatives continue in a hidden generation. */
function Stub({ x, y, dy }: { x: number; y: number; dy: number }) {
  const tip = y + dy;
  const back = tip - Math.sign(dy) * 6;
  return (
    <>
      <path className="stub" d={`M${x} ${y} L${x} ${tip}`} />
      <path className="stub-arrow" d={`M${x - 4} ${back} L${x} ${tip} L${x + 4} ${back}`} />
    </>
  );
}
