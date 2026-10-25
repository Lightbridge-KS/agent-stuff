import assert from "node:assert/strict";
import test from "node:test";
import {
  intersects,
  placeLabel,
  route,
  segmentHits,
} from "../diagram/geometry.ts";

const canvas = { width: 400, height: 500 };
const a = { x: 50, y: 50, width: 100, height: 60 };
test("straight routes use facing borders with four pixel clearance", () => {
  const b = { ...a, x: 250 };
  assert.deepEqual(route(a, b, [], canvas)?.points, [
    { x: 154, y: 80 },
    { x: 246, y: 80 },
  ]);
});
test("a vertical dependency routes around an intervening node", () => {
  const b = { ...a, y: 350 },
    obstacle = { x: 36, y: 180, width: 328, height: 80 };
  const result = route(a, b, [obstacle], canvas);
  assert(result);
  assert.equal(result.kind, "gutter");
  assert(result.points.some((p) => p.x < obstacle.x || p.x > 364));
  for (let i = 1; i < result.points.length; i++)
    assert(!segmentHits(result.points[i - 1], result.points[i], obstacle));
});
test("an enclosed endpoint fails rather than crossing an obstacle", () => {
  assert.equal(
    route(
      a,
      { ...a, y: 350 },
      [{ x: 0, y: 0, width: 400, height: 160 }],
      canvas,
    ),
    null,
  );
});
test("labels remain in bounds and avoid nodes and earlier labels", () => {
  const path = {
    points: [
      { x: 154, y: 80 },
      { x: 246, y: 80 },
    ],
    kind: "direct",
  };
  const label = placeLabel(
    path,
    { width: 60, height: 20 },
    [a, { ...a, x: 250 }],
    canvas,
  );
  assert.deepEqual(label, { x: 170, y: 70, width: 60, height: 20 });
  const next = placeLabel(path, { width: 60, height: 20 }, [label], canvas);
  assert(next && !intersects(next, label));
  assert.equal(placeLabel(path, { width: 500, height: 20 }, [], canvas), null);
});
test("crossing predicates distinguish disjoint and intersecting segments", () => {
  assert(segmentHits({ x: 0, y: 80 }, { x: 200, y: 80 }, a));
  assert(!segmentHits({ x: 0, y: 20 }, { x: 200, y: 20 }, a));
  assert(!segmentHits({ x: 20, y: 0 }, { x: 20, y: 200 }, a));
});

test("a wide parent connects to branch borders without a shared center crossing", () => {
  const parent = { x: 36, y: 40, width: 328, height: 70 };
  const left = { x: 36, y: 180, width: 130, height: 70 };
  const right = { x: 234, y: 180, width: 130, height: 70 };
  const first = route(parent, left, [right], canvas);
  assert.deepEqual(first.points, [
    { x: 101, y: 114 },
    { x: 101, y: 176 },
  ]);
  assert.deepEqual(route(parent, right, [left], canvas, [first]).points, [
    { x: 299, y: 114 },
    { x: 299, y: 176 },
  ]);
});
test("browser-like sizes with prototype accessors are copied explicitly", () => {
  class Size {
    get width() {
      return 60;
    }
    get height() {
      return 20;
    }
  }
  const result = placeLabel(
    {
      points: [
        { x: 154, y: 80 },
        { x: 246, y: 80 },
      ],
      kind: "direct",
    },
    new Size(),
    [],
    canvas,
  );
  assert.deepEqual(result, { x: 170, y: 70, width: 60, height: 20 });
});
