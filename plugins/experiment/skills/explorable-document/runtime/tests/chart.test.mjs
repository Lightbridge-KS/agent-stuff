import assert from "node:assert/strict";
import test from "node:test";
import { exactValue, totalParts, validateData } from "../chart/model.ts";

const xy = {
  kind: "xy",
  x: { label: "Day", items: [{ id: "a", label: "Monday" }] },
  y: { label: "Latency", unit: "ms" },
  series: [{ id: "s", label: "Sample", values: [null] }],
};
test("models preserve missing observations and reject malformed or ambiguous data", () => {
  assert.equal(validateData(xy), null);
  assert.equal(
    validateData({ ...xy, series: [{ ...xy.series[0], values: [0] }] }),
    null,
  );
  assert.match(
    validateData({ ...xy, series: [{ ...xy.series[0], values: [NaN] }] }),
    /finite/,
  );
  assert.match(
    validateData({ ...xy, series: [{ ...xy.series[0], values: [] }] }),
    /per category/,
  );
  assert.match(
    validateData({
      ...xy,
      x: { ...xy.x, items: [...xy.x.items, ...xy.x.items] },
    }),
    /unique/,
  );
  assert.match(validateData({ ...xy, series: [] }), /1–4/);
  assert.match(validateData({ kind: "alien" }), /xy or parts/);
});
test("parts use counts, retain zeroes and reject negatives, duplicates and overflow", () => {
  const data = {
    kind: "parts",
    unit: "cases",
    segments: [
      { id: "a", label: "A", value: 17 },
      { id: "b", label: "B", value: 8 },
      { id: "c", label: "C", value: 75 },
    ],
  };
  assert.equal(validateData(data), null);
  assert.equal(totalParts(data), 100);
  assert.equal(validateData({ ...data, segments: [] }), null);
  assert.equal(
    totalParts({ ...data, segments: [{ id: "a", label: "A", value: 0 }] }),
    0,
  );
  assert.match(
    validateData({ ...data, segments: [{ id: "a", label: "A", value: -1 }] }),
    /nonnegative/,
  );
  assert.match(
    validateData({ ...data, segments: [data.segments[0], data.segments[0]] }),
    /unique/,
  );
  assert.match(
    validateData({
      ...data,
      segments: [
        { id: "a", label: "A", value: 1e308 },
        { id: "b", label: "B", value: 1e308 },
      ],
    }),
    /total/,
  );
});
test("exact table values do not round or turn missing data into zero", () => {
  assert.equal(exactValue(1.23456789012345), "1.23456789012345");
  assert.equal(exactValue(null), "No observation");
  assert.equal(exactValue(0), "0");
});

import {
  categoryX,
  lineDomain,
  linePath,
  nearestCategory,
  valueY,
  wrapLabel,
} from "../chart/geometry.ts";

test("finite scales contain observations, include zero and handle constants", () => {
  assert.deepEqual(lineDomain([0, 0]).domain, [0, 1]);
  assert.deepEqual(lineDomain([10, 20], { domain: [0, 40] }).domain, [0, 40]);
  assert.equal(valueY(10, [0, 40], 20, 220), 170);
  assert.equal(categoryX(1, 3, 40, 240), 140);
  assert.equal(categoryX(0, 1, 40, 240), 140);
  const signed = lineDomain([-10, 20]);
  assert(signed.domain[0] <= -10 && signed.domain[1] >= 20);
  const constant = lineDomain([5, 5], { includeZero: false });
  assert(constant.domain[0] < 5 && constant.domain[1] > 5);
  assert.match(lineDomain([10], { domain: [0, 5] }), /excludes/);
  assert.match(lineDomain([10], { domain: [5, 5] }), /increasing/);
  assert.match(
    lineDomain([10], { domain: [0, 20], includeZero: false }),
    /either/,
  );
});
test("nulls start a new path rather than connecting gaps, and hit testing is bounded", () => {
  assert.equal(
    linePath([1, null, 3, 4], (value, index) => ({
      x: index * 10,
      y: value * 2,
    })),
    "M 0 2  M 20 6 L 30 8",
  );
  assert.equal(nearestCategory(155, 7, 40, 340), 2);
  assert.equal(nearestCategory(-100, 7, 40, 340), 0);
  assert.equal(nearestCategory(500, 7, 40, 340), 6);
  assert.deepEqual(
    wrapLabel("abcdefgh", 20, (text) => text.length * 5),
    ["abcd", "efgh"],
  );
});

import { partSpans } from "../chart/geometry.ts";
import { displayValue, shareText } from "../chart/model.ts";

test("part geometry uses counts without minimum segment widths or false zero marks", () => {
  assert.deepEqual(partSpans([17, 8, 75], 1000), [
    { x: 0, width: 170 },
    { x: 170, width: 80 },
    { x: 250, width: 750 },
  ]);
  const tiny = partSpans([0.000001, 0, 99.999999], 100);
  assert(tiny[0].width > 0 && tiny[0].width < 0.001);
  assert.equal(tiny[1].width, 0);
  assert.deepEqual(partSpans([0, 0], 100), [
    { x: 0, width: 0 },
    { x: 0, width: 0 },
  ]);
  assert.equal(shareText(0.000001, 100), "<0.1%");
  assert.equal(shareText(0, 0), "Unavailable");
  assert.notEqual(displayValue(0.000001), "0");
});
test("sparse arrays and nonstring tones do not pass model validation", () => {
  assert.match(
    validateData({ ...xy, series: [{ ...xy.series[0], values: Array(1) }] }),
    /finite/,
  );
  assert.match(
    validateData({ ...xy, x: { label: "X", items: Array(1) } }),
    /categories/,
  );
  assert.match(
    validateData({
      ...xy,
      series: [{ ...xy.series[0], tone: { toString: () => "blue" } }],
    }),
    /valid tones/,
  );
});
