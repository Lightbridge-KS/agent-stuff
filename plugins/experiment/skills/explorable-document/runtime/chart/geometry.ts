/** DOM-free chart arithmetic. Never mutates the supplied observations. */
export type Domain = readonly [number, number];
export type LinePlotProps =
  | { domain?: "auto"; includeZero?: boolean }
  | { domain: Domain; includeZero?: never };
export function lineDomain(
  values: readonly (number | null)[],
  options: LinePlotProps = {},
): { domain: Domain; ticks: number[] } | string {
  const observed = values.filter((v): v is number => v !== null);
  const requested = options.domain;
  if (requested !== undefined && requested !== "auto") {
    if (
      !Array.isArray(requested) ||
      requested.length !== 2 ||
      !requested.every(Number.isFinite) ||
      requested[0] >= requested[1] ||
      !Number.isFinite(requested[1] - requested[0])
    )
      return "Use finite increasing domain bounds.";
    if (options.includeZero !== undefined)
      return "Use either an explicit domain or includeZero, not both.";
    if (observed.some((value) => value < requested[0] || value > requested[1]))
      return "The explicit domain excludes observations; expand it rather than clipping values.";
    return {
      domain: requested,
      ticks: Array.from(
        { length: 5 },
        (_, i) => requested[0] + ((requested[1] - requested[0]) * i) / 4,
      ),
    };
  }
  if (
    options.includeZero !== undefined &&
    typeof options.includeZero !== "boolean"
  )
    return "includeZero must be boolean.";
  let low = observed.length ? Math.min(...observed) : 0,
    high = observed.length ? Math.max(...observed) : 1;
  if (options.includeZero !== false) {
    low = Math.min(0, low);
    high = Math.max(0, high);
  }
  if (low === high) {
    if (low === 0) high = 1;
    else {
      const pad = Math.max(Math.abs(low) * 0.05, Number.MIN_VALUE);
      low -= pad;
      high += pad;
    }
  }
  const span = high - low;
  if (!Number.isFinite(span) || span <= 0)
    return "The numeric range is too large or too small for a finite scale.";
  const power = 10 ** Math.floor(Math.log10(span / 4));
  const multiple = [1, 2, 2.5, 5, 10].find((n) => n * power >= span / 4) || 10;
  const step = power * multiple;
  if (!Number.isFinite(step) || step <= 0)
    return "The numeric range is too small for readable ticks; change units.";
  const min = Math.floor(low / step) * step,
    max = Math.ceil(high / step) * step;
  if (
    !Number.isFinite(min) ||
    !Number.isFinite(max) ||
    !Number.isFinite(max - min) ||
    max <= min
  )
    return "The numeric range exceeds finite scale bounds; change units.";
  const ticks = Array.from(
    { length: Math.min(10, Math.round((max - min) / step) + 1) },
    (_, i) => Number((min + i * step).toPrecision(12)),
  );
  return { domain: [min, max], ticks };
}
export const categoryX = (
  index: number,
  count: number,
  left: number,
  right: number,
): number =>
  count === 1
    ? (left + right) / 2
    : left + (index / (count - 1)) * (right - left);
export const valueY = (
  value: number,
  domain: Domain,
  top: number,
  bottom: number,
): number =>
  bottom - ((value - domain[0]) / (domain[1] - domain[0])) * (bottom - top);
export function nearestCategory(
  x: number,
  count: number,
  left: number,
  right: number,
): number {
  return count <= 1
    ? 0
    : Math.max(
        0,
        Math.min(
          count - 1,
          Math.round(((x - left) / (right - left)) * (count - 1)),
        ),
      );
}
export function linePath(
  values: readonly (number | null)[],
  point: (value: number, index: number) => { x: number; y: number },
): string {
  return values
    .map((value, index) => {
      if (value === null) return "";
      const p = point(value, index);
      return `${!index || values[index - 1] === null ? "M" : "L"} ${p.x} ${p.y}`;
    })
    .join(" ");
}
export function tickText(value: number): string {
  if (value !== 0 && (Math.abs(value) >= 1e9 || Math.abs(value) < 0.001))
    return value.toExponential(2);
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 6 }).format(
    value,
  );
}
export function wrapLabel(
  label: string,
  width: number,
  measure: (text: string) => number,
): string[] {
  const lines: string[] = [];
  let line = "";
  for (const character of label) {
    if (line && measure(line + character) > width) {
      lines.push(line.trim());
      line = character;
    } else line += character;
  }
  if (line.trim()) lines.push(line.trim());
  return lines.length ? lines : [label];
}

export function partSpans(
  values: readonly number[],
  width: number,
): { x: number; width: number }[] {
  const total = values.reduce((sum, value) => sum + value, 0);
  let x = 0;
  return values.map((value) => {
    const size = total ? (value / total) * width : 0;
    const span = { x, width: size };
    x += size;
    return span;
  });
}
