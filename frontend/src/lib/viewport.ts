// Pan/zoom maths. A transform maps tree coordinates to screen pixels:
// screen = tree * k + (x, y).

export interface Transform {
  x: number;
  y: number;
  k: number;
}

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

export const MIN_SCALE = 0.08;
export const MAX_SCALE = 2.5;

export const clampScale = (k: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, k));

/** Fit `content` inside the viewport area `view` (screen pixels) with padding. */
export function fitTransform(content: Box, view: Box, padding = 32, maxScale = 1.2): Transform {
  const width = Math.max(1, view.width - 2 * padding);
  const height = Math.max(1, view.height - 2 * padding);
  const k = clampScale(Math.min(width / Math.max(content.width, 1), height / Math.max(content.height, 1), maxScale));
  return {
    k,
    x: view.x + (view.width - content.width * k) / 2 - content.x * k,
    y: view.y + (view.height - content.height * k) / 2 - content.y * k,
  };
}

/** Zoom by `factor` keeping the screen point (px, py) fixed. */
export function zoomAt(t: Transform, factor: number, px: number, py: number): Transform {
  const k = clampScale(t.k * factor);
  const ratio = k / t.k;
  return { k, x: px - (px - t.x) * ratio, y: py - (py - t.y) * ratio };
}

/** Smallest pan that brings `box` (tree coords) inside `safe` (screen coords). */
export function panIntoView(t: Transform, box: Box, safe: Box, margin = 24): Transform {
  const left = box.x * t.k + t.x;
  const top = box.y * t.k + t.y;
  const right = left + box.width * t.k;
  const bottom = top + box.height * t.k;
  let dx = 0;
  let dy = 0;
  if (left < safe.x + margin) dx = safe.x + margin - left;
  else if (right > safe.x + safe.width - margin) dx = safe.x + safe.width - margin - right;
  if (top < safe.y + margin) dy = safe.y + margin - top;
  else if (bottom > safe.y + safe.height - margin) dy = safe.y + safe.height - margin - bottom;
  return dx || dy ? { ...t, x: t.x + dx, y: t.y + dy } : t;
}

export function boundsOf(boxes: Box[]): Box | null {
  if (!boxes.length) return null;
  let x1 = Infinity;
  let y1 = Infinity;
  let x2 = -Infinity;
  let y2 = -Infinity;
  for (const b of boxes) {
    x1 = Math.min(x1, b.x);
    y1 = Math.min(y1, b.y);
    x2 = Math.max(x2, b.x + b.width);
    y2 = Math.max(y2, b.y + b.height);
  }
  return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
}
