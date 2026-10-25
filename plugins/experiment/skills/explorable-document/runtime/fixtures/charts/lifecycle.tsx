import { ChartFrame, LinePlot, type XYData } from "@explorable/kit";
import { useState } from "react";
import { comparison } from "./examples";
export default function Lifecycle() {
  const [mode, setMode] = useState("normal"),
    [selection, setSelection] = useState<string | null>("mon"),
    [calls, setCalls] = useState(0),
    [source, setSource] = useState("none");
  let data: XYData = comparison;
  if (mode === "removed")
    data = {
      ...comparison,
      x: { ...comparison.x, items: comparison.x.items.slice(1) },
      series: comparison.series.map((s) => ({
        ...s,
        values: s.values.slice(1),
      })),
    };
  if (mode === "empty")
    data = {
      ...comparison,
      x: { ...comparison.x, items: [] },
      series: comparison.series.map((s) => ({ ...s, values: [] })),
    };
  if (mode === "all-null")
    data = {
      ...comparison,
      series: comparison.series.map((s) => ({
        ...s,
        values: s.values.map(() => null),
      })),
    };
  if (mode === "one")
    data = {
      ...comparison,
      x: { ...comparison.x, items: comparison.x.items.slice(0, 1) },
      series: comparison.series.map((s) => ({
        ...s,
        values: s.values.slice(0, 1),
      })),
    };
  if (mode === "signed")
    data = {
      ...comparison,
      series: [
        {
          id: "signed",
          label: "Signed values",
          values: [-10, 0, 20, -5, 3, 1, -2],
        },
      ],
    };
  if (mode === "zero")
    data = {
      ...comparison,
      series: [
        { id: "zero", label: "Zero values", values: [0, 0, 0, 0, 0, 0, 0] },
      ],
    };
  if (mode === "constant")
    data = {
      ...comparison,
      series: [
        { id: "constant", label: "Constant", values: [5, 5, 5, 5, 5, 5, 5] },
      ],
    };
  if (mode === "long")
    data = {
      ...comparison,
      x: {
        label: "Observation category with descriptive labels",
        items: comparison.x.items.map((item) => ({
          ...item,
          label: `${item.label}: a deliberately long category label that wraps without losing the complete text`,
        })),
      },
    };
  if (mode === "duplicate")
    data = {
      ...comparison,
      x: {
        ...comparison.x,
        items: [comparison.x.items[0], comparison.x.items[0]],
      },
    };
  if (mode === "nonfinite")
    data = {
      ...comparison,
      series: [{ id: "bad", label: "Bad", values: [NaN, 0, 0, 0, 0, 0, 0] }],
    };
  if (mode === "four")
    data = {
      ...comparison,
      series: [0, 1, 2, 3].map((n) => ({
        id: `s${n}`,
        label: `Series ${n + 1}`,
        tone: "blue",
        values: [
          100 + n * 10,
          120 + n * 10,
          110 + n * 10,
          130 + n * 10,
          140 + n * 10,
          150 + n * 10,
          160 + n * 10,
        ],
      })),
    };
  return (
    <>
      <div className="actions">
        <label>
          Fixture mode{" "}
          <select
            id="fixture-mode"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            {[
              "normal",
              "removed",
              "empty",
              "all-null",
              "one",
              "signed",
              "zero",
              "constant",
              "long",
              "duplicate",
              "nonfinite",
              "hidden",
              "domain",
              "four",
            ].map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          id="repair"
          onClick={() => setSelection(data.x.items[0]?.id || null)}
        >
          Repair selection
        </button>
      </div>
      <p id="selection-note">
        {calls} callbacks · {selection || "none"} · {source}
      </p>
      <div style={{ display: mode === "hidden" ? "none" : undefined }}>
        <ChartFrame
          title="Controlled chart"
          summary="Selection belongs to the author; lifecycle state is synthetic."
          data={data}
          selectedId={mode === "empty" ? null : selection}
          onSelectionChange={(change) => {
            setSelection(change.id);
            setSource(change.source);
            setCalls((count) => count + 1);
          }}
        >
          <LinePlot
            {...(mode === "domain" ? { domain: [0, 10] as const } : {})}
          />
        </ChartFrame>
        <ChartFrame
          title="Independent uncontrolled chart"
          summary="The same category IDs can be reused in another frame."
          data={data}
        >
          <LinePlot />
        </ChartFrame>
      </div>
    </>
  );
}
