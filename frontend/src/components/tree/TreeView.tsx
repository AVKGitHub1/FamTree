import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { cardLines } from "../../lib/attributes";
import { continuations, inRange, visibleConnectors, type RowRange } from "../../lib/generations";
import type { TreeIndex } from "../../lib/treeIndex";
import {
  boundsOf,
  fitTransform,
  panIntoView,
  zoomAt,
  type Box,
  type Transform,
} from "../../lib/viewport";
import type { MenuItem } from "../ui/Menu";
import { Connectors } from "./Connectors";
import { PersonCard } from "./PersonCard";

export interface Occlusion {
  top: number; // px used by floating controls along the top (small screens)
  right: number; // px covered on the right (side panel)
  bottom: number; // px covered at the bottom (bottom sheet on small screens)
  left: number; // px used by floating controls along the left
}

interface Props {
  index: TreeIndex;
  range: RowRange;
  selectedId: string | null;
  picks: { first: string | null; second: string | null };
  highlight: { people: Set<string>; links: Set<string> };
  occlusion: Occlusion;
  fitRequest: number;
  /** Zoom in to at least this scale around a newly selected card (small screens). */
  focusScale: number | null;
  menuFor: (id: string) => MenuItem[];
  onActivate: (id: string) => void;
  onBackground: () => void;
  describe: (id: string) => string;
}

const DRAG_THRESHOLD = 4;

export function TreeView(props: Props) {
  const { index, range, selectedId, picks, highlight, occlusion, fitRequest, focusScale } = props;
  const viewportRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef(new Map<string, HTMLDivElement>());
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [transform, setTransform] = useState<Transform>({ x: 0, y: 0, k: 1 });

  const layout = index.data.layout;
  const visibleIds = useMemo(
    () => Object.keys(layout.nodes).filter((id) => inRange(layout.nodes[id].row, range)),
    [layout, range],
  );
  const connectors = useMemo(() => visibleConnectors(index, range), [index, range]);
  const crossings = useMemo(() => {
    const shown = new Set(connectors.map((c) => c.id));
    return layout.crossings.filter((x) => shown.has(x.over) && shown.has(x.under));
  }, [layout, connectors]);
  const marks = useMemo(() => continuations(index, range), [index, range]);
  const lines = useMemo(
    () => new Map(index.data.people.map((p) => [p.id, cardLines(p, index.definitions)])),
    [index],
  );

  // Area not covered by the side panel / bottom sheet / floating controls.
  const safeArea = useCallback(
    (): Box => ({
      x: occlusion.left,
      y: occlusion.top,
      width: Math.max(80, size.width - occlusion.left - occlusion.right),
      height: Math.max(80, size.height - occlusion.top - occlusion.bottom),
    }),
    [size, occlusion],
  );

  const fitTarget = useCallback((): Transform | null => {
    const bounds = boundsOf(visibleIds.map((id) => layout.nodes[id]));
    return bounds && size.width ? fitTransform(bounds, safeArea()) : null;
  }, [visibleIds, layout, size.width, safeArea]);

  const fitVisible = useCallback(() => {
    const target = fitTarget();
    if (target) setTransform(target);
  }, [fitTarget]);

  useLayoutEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) =>
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height }),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Adjust the view when its inputs change, during render rather than in an
  // effect (https://react.dev/learn/you-might-not-need-an-effect):
  // * fit once when the tree first has room to draw; later edits keep the view;
  // * refit on an explicit request or a change of generation filter;
  // * show a highlighted relation path in full;
  // * otherwise keep a newly selected card visible and clear of panels.
  const viewKey = `${fitRequest}|${range.lo}|${range.hi}`;
  const pathKey = [...highlight.people].sort().join(",");
  const [seen, setSeen] = useState<{ viewKey: string; pathKey: string; selectedId: string | null } | null>(null);
  if (size.width && visibleIds.length) {
    const now = { viewKey, pathKey, selectedId };
    if (!seen || seen.viewKey !== viewKey) {
      setSeen(now);
      const target = fitTarget();
      if (target) setTransform(target);
    } else if (seen.pathKey !== pathKey) {
      setSeen(now);
      const bounds = boundsOf([...highlight.people].flatMap((id) => (layout.nodes[id] ? [layout.nodes[id]] : [])));
      if (bounds) setTransform((t) => panIntoView(t, bounds, safeArea()) === t ? t : fitTransform(bounds, safeArea(), 48, 1));
    } else if (seen.selectedId !== selectedId) {
      setSeen(now);
      const node = selectedId ? layout.nodes[selectedId] : undefined;
      if (node) {
        const area = safeArea();
        setTransform((t) => {
          if (focusScale && t.k < focusScale) {
            // Centre the card at a readable size within the uncovered area.
            const k = focusScale;
            return {
              k,
              x: area.x + area.width / 2 - (node.x + node.width / 2) * k,
              y: area.y + area.height / 2 - (node.y + node.height / 2) * k,
            };
          }
          return panIntoView(t, node, area);
        });
      }
    }
  }

  // --- pan & zoom ------------------------------------------------------------
  // Drags may start anywhere, cards included (needed on touch screens). The
  // pointer is captured only once it has really moved, so a tap still reaches
  // the card under it and a drag never activates one.
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef({ moved: false, onBackground: false, pinch: null as number | null, start: { x: 0, y: 0 } });

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      const factor = Math.exp(-event.deltaY * (event.ctrlKey ? 0.01 : 0.0015));
      setTransform((t) => zoomAt(t, factor, event.clientX - rect.left, event.clientY - rect.top));
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, []);

  const local = (event: { clientX: number; clientY: number }) => {
    const rect = viewportRef.current!.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  const onPointerDown = (event: React.PointerEvent) => {
    const target = event.target as HTMLElement;
    if (target.closest("button, .legend, .menu__list")) return;
    const point = local(event);
    pointers.current.set(event.pointerId, point);
    if (pointers.current.size === 1) {
      gesture.current = { moved: false, onBackground: !target.closest(".card"), pinch: null, start: point };
    }
  };

  const onPointerMove = (event: React.PointerEvent) => {
    const previous = pointers.current.get(event.pointerId);
    if (!previous) return;
    const point = local(event);
    if (pointers.current.size === 2) {
      pointers.current.set(event.pointerId, point);
      const [a, b] = [...pointers.current.values()];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      const last = gesture.current.pinch;
      gesture.current.pinch = distance;
      if (!gesture.current.moved) {
        gesture.current.moved = true;
        viewportRef.current?.setPointerCapture(event.pointerId);
      }
      if (last) setTransform((t) => zoomAt(t, distance / last, (a.x + b.x) / 2, (a.y + b.y) / 2));
      return;
    }
    if (!gesture.current.moved) {
      const { start } = gesture.current;
      if (Math.hypot(point.x - start.x, point.y - start.y) < DRAG_THRESHOLD) return;
      gesture.current.moved = true;
      viewportRef.current?.setPointerCapture(event.pointerId);
    }
    pointers.current.set(event.pointerId, point);
    setTransform((t) => ({ ...t, x: t.x + point.x - previous.x, y: t.y + point.y - previous.y }));
  };

  const onPointerUp = (event: React.PointerEvent) => {
    if (!pointers.current.delete(event.pointerId)) return;
    if (pointers.current.size < 2) gesture.current.pinch = null;
    if (pointers.current.size === 0 && gesture.current.onBackground && !gesture.current.moved) {
      props.onBackground();
    }
  };

  const zoomBy = (factor: number) =>
    setTransform((t) => zoomAt(t, factor, size.width / 2, size.height / 2));

  const onViewportKey = (event: KeyboardEvent) => {
    if (event.target !== viewportRef.current) return;
    const step = 60;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [step, 0],
      ArrowRight: [-step, 0],
      ArrowUp: [0, step],
      ArrowDown: [0, -step],
    };
    if (event.key in moves) {
      event.preventDefault();
      const [dx, dy] = moves[event.key];
      setTransform((t) => ({ ...t, x: t.x + dx, y: t.y + dy }));
    } else if (event.key === "+" || event.key === "=") zoomBy(1.2);
    else if (event.key === "-") zoomBy(1 / 1.2);
    else if (event.key === "0") fitVisible();
  };

  // --- keyboard navigation between cards ----------------------------------------
  const registerRef = useCallback((id: string, element: HTMLDivElement | null) => {
    if (element) cardRefs.current.set(id, element);
    else cardRefs.current.delete(id);
  }, []);

  const onNavigate = useCallback(
    (id: string, key: string) => {
      const node = layout.nodes[id];
      let target: string | undefined;
      if (key === "ArrowLeft" || key === "ArrowRight") {
        const row = index.rows[node.row] ?? [];
        target = row[row.indexOf(id) + (key === "ArrowLeft" ? -1 : 1)];
      } else {
        const rowIndex = node.row + (key === "ArrowUp" ? -1 : 1);
        if (inRange(rowIndex, range)) {
          const centre = node.x + node.width / 2;
          target = (index.rows[rowIndex] ?? []).reduce<string | undefined>((best, candidate) => {
            const c = layout.nodes[candidate];
            const b = best ? layout.nodes[best] : undefined;
            const dist = (n: typeof c) => Math.abs(n.x + n.width / 2 - centre);
            return !b || dist(c) < dist(b) ? candidate : best;
          }, undefined);
        }
      }
      if (!target) return;
      cardRefs.current.get(target)?.focus({ preventScroll: true });
      setTransform((t) => panIntoView(t, layout.nodes[target], safeArea()));
    },
    [index, layout, range, safeArea],
  );

  return (
    <div
      ref={viewportRef}
      className="viewport"
      tabIndex={0}
      aria-label="Family tree. Drag or use arrow keys to move, plus and minus to zoom, 0 to fit."
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onKeyDown={onViewportKey}
    >
      <div
        className="stage"
        style={{
          width: layout.width,
          height: layout.height,
          transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.k})`,
          ["--zoom" as string]: transform.k,
        }}
      >
        <Connectors
          index={index}
          connectors={connectors}
          crossings={crossings}
          continuations={marks}
          highlightLinks={highlight.links}
        />
        {visibleIds.map((id) => {
          const person = index.people.get(id);
          if (!person) return null;
          const pick = picks.first === id ? 1 : picks.second === id ? 2 : null;
          return (
            <PersonCard
              key={id}
              person={person}
              node={layout.nodes[id]}
              lines={lines.get(id) ?? []}
              selected={selectedId === id}
              pick={pick}
              onPath={highlight.people.has(id)}
              menuItems={selectedId === id ? props.menuFor(id) : null}
              description={props.describe(id)}
              onActivate={props.onActivate}
              onNavigate={onNavigate}
              registerRef={registerRef}
            />
          );
        })}
      </div>
      <div className="zoom-controls" role="group" aria-label="Zoom">
        <button type="button" className="control-button" aria-label="Zoom in" onClick={() => zoomBy(1.25)}>
          +
        </button>
        <button type="button" className="control-button" aria-label="Zoom out" onClick={() => zoomBy(0.8)}>
          −
        </button>
        <button
          type="button"
          className="control-button control-button--text"
          aria-label="Fit the shown generations to the screen"
          onClick={fitVisible}
        >
          Fit
        </button>
      </div>
    </div>
  );
}
