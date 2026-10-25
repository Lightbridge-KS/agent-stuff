import { ChartFrame, type XYData } from "@explorable/kit";

const xy: XYData = {
  kind: "xy",
  x: {
    label: "Day",
    items: [
      { id: "mon", label: "Monday" },
      { id: "tue", label: "Tuesday" },
    ],
  },
  y: { label: "Latency", unit: "ms" },
  series: [{ id: "base", label: "Baseline", values: [1.23456789012345, null] }],
};
export default function FrameFixture() {
  return (
    <>
      <ChartFrame
        title="Frame data contract"
        summary="A precise value and a missing observation share one model."
        data={xy}
      >
        <p>Custom plot slot</p>
      </ChartFrame>
      <ChartFrame
        title="Parts frame"
        summary="Counts, zero values and proportions remain available as HTML."
        data={{
          kind: "parts",
          unit: "cases",
          segments: [
            { id: "yes", label: "Observed", value: 10 },
            { id: "zero", label: "Zero", value: 0 },
          ],
        }}
      >
        <p>Custom plot slot</p>
      </ChartFrame>
      <ChartFrame
        title="Empty frame"
        summary="An empty category list is valid."
        data={{
          ...xy,
          x: { ...xy.x, items: [] },
          series: [{ ...xy.series[0], values: [] }],
        }}
      >
        <p>No observations to plot.</p>
      </ChartFrame>
    </>
  );
}
