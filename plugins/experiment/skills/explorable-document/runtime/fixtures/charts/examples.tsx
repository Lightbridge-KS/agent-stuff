import {
  ChartFrame,
  LinePlot,
  type PartsData,
  SegmentedBar,
  type XYData,
} from "@explorable/kit";
import { useState } from "react";

const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const requests = [1100, 1450, 1320, 1800, 2300, 2050, 2750];
export const errors = [18, 24, 15, 12, 20, 9, 7];
export const baseline = [120, 150, null, 180, 190, 160, 170];
export const candidate = [110, 135, 130, 170, 165, 155, 150];
export const items = days.map((label) => ({ id: label.toLowerCase(), label }));
export const comparison: XYData = {
  kind: "xy",
  x: { label: "Day", items },
  y: { label: "Response time", unit: "ms" },
  series: [
    { id: "baseline", label: "Baseline", values: baseline },
    { id: "candidate", label: "Candidate", values: candidate },
  ],
};
export function Trend() {
  const [metric, setMetric] = useState("Requests");
  const data: XYData = {
    kind: "xy",
    x: { label: "Day", items },
    y: { label: metric, unit: `${metric.toLowerCase()}/day` },
    series: [
      {
        id: metric.toLowerCase(),
        label: metric,
        values: metric === "Requests" ? requests : errors,
      },
    ],
  };
  return (
    <ChartFrame
      title="Agent performance"
      summary={
        metric === "Requests"
          ? "Requests increase from 1,100 on Monday to 2,750 on Sunday."
          : "Errors fluctuate and decrease from 18 on Monday to 7 on Sunday."
      }
      data={data}
      controls={
        <fieldset className="actions">
          <legend>Metric</legend>
          {["Requests", "Errors"].map((label) => (
            <button
              id={`series-${label}`}
              key={label}
              type="button"
              aria-pressed={metric === label}
              onClick={() => setMetric(label)}
            >
              {label}
            </button>
          ))}
        </fieldset>
      }
      note="Synthetic 7-day data. Requests approximate the supplied screenshot; Errors values are invented."
    >
      <LinePlot />
    </ChartFrame>
  );
}
export function Comparison() {
  return (
    <ChartFrame
      title="Response time comparison"
      summary="The candidate is lower on Sunday. Baseline has no Wednesday observation."
      data={comparison}
      defaultSelectedId="wed"
      note="Synthetic comparison on one shared scale; missing observations break the line."
    >
      <LinePlot domain={[0, 200]} />
    </ChartFrame>
  );
}

export function Parts() {
  const [mode, setMode] = useState("counts");
  let segments: PartsData["segments"] = [
    { id: "tp", label: "True positive", value: 17, tone: "teal" },
    { id: "fp", label: "False positive", value: 8, tone: "red" },
    { id: "negative", label: "Test negative", value: 75, tone: "blue" },
  ];
  if (mode === "zero") segments = segments.map((s) => ({ ...s, value: 0 }));
  if (mode === "empty") segments = [];
  if (mode === "tiny")
    segments = [
      { id: "tiny", label: "Tiny nonzero segment", value: 0.000001 },
      { id: "zero", label: "Zero segment", value: 0 },
      { id: "rest", label: "Remaining cases", value: 99.999999 },
    ];
  if (mode === "precision")
    segments = [
      { id: "precise", label: "Precise value", value: 1.23456789012345 },
      { id: "other", label: "Other", value: 2 },
    ];
  if (mode === "long")
    segments = segments.map((s) => ({
      ...s,
      label: `${s.label}: a long descriptive category label that stays available on a small screen`,
    }));
  if (mode === "negative")
    segments = [{ id: "bad", label: "Invalid negative count", value: -1 }];
  if (mode === "duplicate") segments = [segments[0], segments[0]];
  return (
    <ChartFrame
      title="Expected outcomes"
      summary={
        mode === "counts"
          ? "Illustrative expected counts for a population of 100."
          : `Synthetic ${mode} state for chart acceptance.`
      }
      data={{ kind: "parts", unit: "expected cases", segments }}
      controls={
        <label>
          Example{" "}
          <select
            id="parts-mode"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            {[
              "counts",
              "tiny",
              "zero",
              "empty",
              "precision",
              "long",
              "negative",
              "duplicate",
            ].map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
      }
      note="Synthetic arithmetic. Test negative includes true negatives and false negatives."
    >
      <SegmentedBar />
    </ChartFrame>
  );
}
