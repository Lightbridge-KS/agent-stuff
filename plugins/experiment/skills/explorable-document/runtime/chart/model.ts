/** Chart values are the shared source for drawing, inspection, legends and tables. */
export type ChartTone = "blue" | "teal" | "orange" | "red" | "neutral";
export type XYData = {
  kind: "xy";
  x: { label: string; items: readonly { id: string; label: string }[] };
  y: { label: string; unit: string };
  series: readonly {
    id: string;
    label: string;
    tone?: ChartTone;
    values: readonly (number | null)[];
  }[];
};
export type PartsData = {
  kind: "parts";
  unit: string;
  segments: readonly {
    id: string;
    label: string;
    value: number;
    tone?: ChartTone;
  }[];
};
export type ChartData = XYData | PartsData;
const tones = ["blue", "teal", "orange", "red", "neutral"];
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const text = (value: unknown): value is string =>
  typeof value === "string" && !!value.trim();
const finite = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
function entries(
  value: unknown,
  limit: number,
): value is Record<string, unknown>[] {
  return (
    Array.isArray(value) &&
    value.length <= limit &&
    Array.from(value).every(
      (item) =>
        record(item) &&
        text(item.id) &&
        text(item.label) &&
        (item.tone === undefined ||
          (typeof item.tone === "string" && tones.includes(item.tone))),
    ) &&
    new Set(value.map((item) => item.id)).size === value.length
  );
}
export function validateData(value: unknown): string | null {
  if (!record(value)) return "Supply an xy or parts dataset.";
  if (value.kind === "xy") {
    if (
      !record(value.x) ||
      !text(value.x.label) ||
      !entries(value.x.items, 200)
    )
      return "XY needs an X label and at most 200 categories with unique nonempty IDs and labels.";
    if (!record(value.y) || !text(value.y.label) || !text(value.y.unit))
      return "XY needs a Y label and unit.";
    if (!entries(value.series, 4) || value.series.length < 1)
      return "XY needs 1–4 series with unique IDs, labels and valid tones.";
    const count = value.x.items.length;
    if (
      !value.series.every(
        (s) =>
          Array.isArray(s.values) &&
          s.values.length === count &&
          Array.from(s.values).every((v) => v === null || finite(v)),
      )
    )
      return "Each series needs one finite number or null per category; do not omit or impute observations.";
    const values = value.series
      .flatMap((s) => s.values as (number | null)[])
      .filter((v): v is number => v !== null);
    if (
      values.length &&
      !Number.isFinite(Math.max(...values) - Math.min(...values))
    )
      return "The XY numeric range is too large to draw with finite coordinates.";
    return null;
  }
  if (value.kind === "parts") {
    if (!text(value.unit) || !entries(value.segments, 8))
      return "Parts needs a unit and at most eight segments with unique IDs, labels and valid tones.";
    if (!value.segments.every((s) => finite(s.value) && s.value >= 0))
      return "Segment counts must be finite and nonnegative.";
    if (
      !Number.isFinite(
        value.segments.reduce((sum, s) => sum + Number(s.value), 0),
      )
    )
      return "The segment total exceeds the finite numeric range.";
    return null;
  }
  return "Dataset kind must be xy or parts.";
}
export function totalParts(data: PartsData): number {
  return data.segments.reduce((sum, item) => sum + item.value, 0);
}
export function toneFor(tone: ChartTone | undefined, index: number): ChartTone {
  return tone || (["blue", "teal", "orange", "red"] as const)[index % 4];
}
export function displayValue(value: number | null): string {
  if (value === null) return "No observation";
  return new Intl.NumberFormat(
    "en-US",
    value !== 0 && Math.abs(value) < 0.001
      ? { notation: "scientific", maximumSignificantDigits: 3 }
      : { maximumFractionDigits: 3 },
  ).format(value);
}
export function shareText(value: number, total: number): string {
  if (!total) return "Unavailable";
  const share = (value / total) * 100;
  return value > 0 && share < 0.1 ? "<0.1%" : `${share.toFixed(1)}%`;
}
export function exactValue(value: number | null): string {
  return value === null ? "No observation" : String(value);
}
