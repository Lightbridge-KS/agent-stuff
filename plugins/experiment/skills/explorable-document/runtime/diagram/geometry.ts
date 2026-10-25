/** Bounded orthogonal routing in diagram-local CSS pixels. No DOM dependencies. */
export type Point = { x: number; y: number };
export type Rect = { x: number; y: number; width: number; height: number };
export type Route = { points: Point[]; kind: "direct" | "elbow" | "gutter" };
type Side = "left" | "right" | "top" | "bottom";
const sides: Side[] = ["right", "bottom", "left", "top"];
const right = (r: Rect) => r.x + r.width;
const bottom = (r: Rect) => r.y + r.height;
const close = (a: number, b: number) => Math.abs(a - b) < 0.1;
export function intersects(a: Rect, b: Rect, margin = 0): boolean {
  return (
    a.x < right(b) + margin &&
    right(a) > b.x - margin &&
    a.y < bottom(b) + margin &&
    bottom(a) > b.y - margin
  );
}
export function segmentHits(a: Point, b: Point, r: Rect, margin = 2): boolean {
  if (close(a.x, b.x))
    return (
      a.x > r.x - margin &&
      a.x < right(r) + margin &&
      Math.max(a.y, b.y) > r.y - margin &&
      Math.min(a.y, b.y) < bottom(r) + margin
    );
  if (close(a.y, b.y))
    return (
      a.y > r.y - margin &&
      a.y < bottom(r) + margin &&
      Math.max(a.x, b.x) > r.x - margin &&
      Math.min(a.x, b.x) < right(r) + margin
    );
  return true; // The router never permits a diagonal segment.
}
function anchor(r: Rect, side: Side, other: Rect): Point {
  // Project into the shared span of facing borders. Wide parent cards can then
  // connect directly to each branch instead of forcing all edges through a center port.
  const left = Math.max(r.x, other.x),
    top = Math.max(r.y, other.y);
  const endX = Math.min(right(r), right(other)),
    endY = Math.min(bottom(r), bottom(other));
  const x = endX > left ? (left + endX) / 2 : r.x + r.width / 2;
  const y = endY > top ? (top + endY) / 2 : r.y + r.height / 2;
  if (side === "left") return { x: r.x - 4, y };
  if (side === "right") return { x: right(r) + 4, y };
  if (side === "top") return { x, y: r.y - 4 };
  return { x, y: bottom(r) + 4 };
}
function outward(a: Point, b: Point, side: Side): boolean {
  if (side === "left") return close(a.y, b.y) && b.x < a.x;
  if (side === "right") return close(a.y, b.y) && b.x > a.x;
  if (side === "top") return close(a.x, b.x) && b.y < a.y;
  return close(a.x, b.x) && b.y > a.y;
}
function simplify(points: Point[]): Point[] {
  const unique = points.filter(
    (p, i) =>
      !i || !close(p.x, points[i - 1].x) || !close(p.y, points[i - 1].y),
  );
  return unique.filter(
    (p, i) =>
      !i ||
      i === unique.length - 1 ||
      !(
        (close(unique[i - 1].x, p.x) && close(p.x, unique[i + 1].x)) ||
        (close(unique[i - 1].y, p.y) && close(p.y, unique[i + 1].y))
      ),
  );
}
function crossing(a: Point, b: Point, c: Point, d: Point): boolean {
  const av = close(a.x, b.x),
    cv = close(c.x, d.x);
  if (av === cv) {
    if (av && close(a.x, c.x))
      return (
        Math.min(Math.max(a.y, b.y), Math.max(c.y, d.y)) -
          Math.max(Math.min(a.y, b.y), Math.min(c.y, d.y)) >
        1
      );
    if (!av && close(a.y, c.y))
      return (
        Math.min(Math.max(a.x, b.x), Math.max(c.x, d.x)) -
          Math.max(Math.min(a.x, b.x), Math.min(c.x, d.x)) >
        1
      );
    return false;
  }
  const [v1, v2, h1, h2] = av ? [a, b, c, d] : [c, d, a, b];
  return (
    v1.x > Math.min(h1.x, h2.x) + 0.1 &&
    v1.x < Math.max(h1.x, h2.x) - 0.1 &&
    h1.y > Math.min(v1.y, v2.y) + 0.1 &&
    h1.y < Math.max(v1.y, v2.y) - 0.1
  );
}
export function route(
  from: Rect,
  to: Rect,
  obstacles: Rect[],
  canvas: { width: number; height: number },
  previous: Route[] = [],
): Route | null {
  const candidates: { route: Route; score: number }[] = [];
  for (const sa of sides)
    for (const sb of sides) {
      const a = anchor(from, sa, to),
        b = anchor(to, sb, from);
      const paths: Route[] = [];
      if (close(a.x, b.x) || close(a.y, b.y))
        paths.push({ points: [a, b], kind: "direct" });
      paths.push(
        { points: [a, { x: b.x, y: a.y }, b], kind: "elbow" },
        { points: [a, { x: a.x, y: b.y }, b], kind: "elbow" },
      );
      for (const x of [
        (a.x + b.x) / 2,
        12,
        20,
        28,
        canvas.width - 12,
        canvas.width - 20,
        canvas.width - 28,
      ])
        paths.push({
          points: [a, { x, y: a.y }, { x, y: b.y }, b],
          kind: x > 28 && x < canvas.width - 28 ? "elbow" : "gutter",
        });
      for (const y of [
        (a.y + b.y) / 2,
        12,
        20,
        28,
        canvas.height - 12,
        canvas.height - 20,
        canvas.height - 28,
      ])
        paths.push({
          points: [a, { x: a.x, y }, { x: b.x, y }, b],
          kind: y > 28 && y < canvas.height - 28 ? "elbow" : "gutter",
        });
      for (const candidate of paths) {
        const points = simplify(candidate.points);
        if (
          points.length < 2 ||
          !outward(points[0], points[1], sa) ||
          !outward(points[points.length - 1], points[points.length - 2], sb)
        )
          continue;
        if (
          points.some(
            (p) =>
              p.x < 4 ||
              p.y < 4 ||
              p.x > canvas.width - 4 ||
              p.y > canvas.height - 4,
          )
        )
          continue;
        let length = 0,
          crosses = 0,
          blocked = false;
        for (let i = 1; i < points.length; i++) {
          const p = points[i - 1],
            q = points[i];
          if ([from, to, ...obstacles].some((r) => segmentHits(p, q, r))) {
            blocked = true;
            break;
          }
          length += Math.abs(q.x - p.x) + Math.abs(q.y - p.y);
          for (const old of previous)
            for (let j = 1; j < old.points.length; j++)
              if (crossing(p, q, old.points[j - 1], old.points[j])) crosses++;
        }
        if (!blocked && crosses === 0)
          candidates.push({
            route: { ...candidate, points },
            score:
              length +
              (points.length - 2) * 20 +
              crosses * 10000 +
              (candidate.kind === "gutter" ? 50 : 0),
          });
      }
    }
  candidates.sort((a, b) => a.score - b.score);
  return candidates[0]?.route || null;
}
export function placeLabel(
  path: Route,
  size: { width: number; height: number },
  obstacles: Rect[],
  canvas: { width: number; height: number },
): Rect | null {
  for (let i = 1; i < path.points.length; i++) {
    const a = path.points[i - 1],
      b = path.points[i];
    const vertical = close(a.x, b.x);
    const centers: Point[] = [{ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }];
    // Prefer the midpoint, then gaps beside obstacles along this segment.
    for (const obstacle of obstacles) {
      if (vertical)
        for (const y of [
          obstacle.y - size.height / 2 - 8,
          bottom(obstacle) + size.height / 2 + 8,
        ]) {
          if (y > Math.min(a.y, b.y) && y < Math.max(a.y, b.y))
            centers.push({ x: a.x, y });
        }
    }
    for (const mid of centers)
      for (const [dx, dy] of [
        [0, 0],
        [0, -(size.height + 8)],
        [0, size.height + 8],
        [-(size.width / 2 + 8), 0],
        [size.width / 2 + 8, 0],
      ]) {
        const rect = {
          x: mid.x - size.width / 2 + dx,
          y: mid.y - size.height / 2 + dy,
          width: size.width,
          height: size.height,
        };
        if (
          rect.x < 0 ||
          rect.y < 0 ||
          right(rect) > canvas.width ||
          bottom(rect) > canvas.height
        )
          continue;
        if (!obstacles.some((o) => intersects(rect, o, 4))) return rect;
      }
  }
  return null;
}
