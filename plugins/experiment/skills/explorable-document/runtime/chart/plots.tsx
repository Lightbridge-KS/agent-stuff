import {
  useContext,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ChartContext } from "./context";
import {
  categoryX,
  type LinePlotProps,
  lineDomain,
  linePath,
  nearestCategory,
  partSpans,
  tickText,
  valueY,
  wrapLabel,
} from "./geometry";
import { ChartDiagnostic } from "./index";
import { dashFor, SeriesMark } from "./marks";
import { toneFor, totalParts } from "./model";

export type { LinePlotProps };

function useWidth() {
  const element = useRef<HTMLDivElement>(null),
    [width, setWidth] = useState(0),
    [fontReady, setFontReady] = useState(false);
  useLayoutEffect(() => {
    const el = element.current;
    if (!el) return;
    let disposed = false;
    const update = () => {
      if (!disposed) setWidth(el.clientWidth);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    document.fonts.ready.then(() => {
      if (!disposed) {
        setFontReady(true);
        update();
      }
    });
    return () => {
      disposed = true;
      observer.disconnect();
    };
  }, []);
  return { element, width, fontReady };
}
function textMeasure() {
  const canvas = document.createElement("canvas"),
    context = canvas.getContext("2d");
  if (context) context.font = "12px ui-sans-serif, system-ui, sans-serif";
  return (text: string) => context?.measureText(text).width || text.length * 8;
}
function keyedLines(lines: string[]) {
  let prefix = "";
  return lines.map((text) => {
    prefix += `${text}|`;
    return { text, key: prefix };
  });
}
export function LinePlot(options: LinePlotProps = {}) {
  const scope = useContext(ChartContext),
    id = useId();
  const { element, width, fontReady } = useWidth();
  const requested = options.domain,
    includeZero = options.includeZero;
  const start = useRef<{ x: number; y: number; pointer: number } | null>(null);
  const data = scope?.data.kind === "xy" ? scope.data : null;
  const geometry = useMemo(() => {
    void fontReady; // Font readiness invalidates text measurement even at the same width.
    if (!data || !width) return null;
    const domain = lineDomain(
      data.series.flatMap((s) => s.values),
      { domain: requested, includeZero } as LinePlotProps,
    );
    if (typeof domain === "string") return domain;
    const measure = textMeasure();
    const left = Math.max(
        42,
        ...domain.ticks.map((v) => measure(tickText(v)) + 12),
      ),
      right = width - 14;
    if (right - left < 30)
      return "Not enough room for readable axes; widen the chart container.";
    const yLabel = wrapLabel(
      `${data.y.label} (${data.y.unit})`,
      width,
      measure,
    );
    const top = yLabel.length * 16 + 16,
      bottom = top + 196;
    const widest = Math.max(
      20,
      ...data.x.items.map((item) => measure(item.label)),
    );
    const capacity = Math.max(
      2,
      Math.floor((right - left) / (Math.min(widest, 100) + 20)),
    );
    const stride = Math.max(
      1,
      Math.ceil(Math.max(1, data.x.items.length - 1) / (capacity - 1)),
    );
    const tickIndices = data.x.items
      .map((_, i) => i)
      .filter(
        (i) => i === 0 || i === data.x.items.length - 1 || i % stride === 0,
      );
    const band = Math.max(
      18,
      (right - left) / Math.max(1, tickIndices.length) - 10,
    );
    const ticks = tickIndices.map((index) => ({
      index,
      lines: keyedLines(wrapLabel(data.x.items[index].label, band, measure)),
    }));
    const lineCount = Math.max(1, ...ticks.map((t) => t.lines.length));
    const xLabel = wrapLabel(data.x.label, width, measure);
    return {
      ...domain,
      yTicks: domain.ticks,
      left,
      right,
      top,
      bottom,
      ticks,
      yLabel: keyedLines(yLabel),
      xLabel: keyedLines(xLabel),
      height: bottom + 26 + lineCount * 16 + xLabel.length * 16 + 12,
    };
  }, [data, width, requested, includeZero, fontReady]);
  if (!scope || !data)
    return (
      <ChartDiagnostic>
        LinePlot needs a ChartFrame with xy data.
      </ChartDiagnostic>
    );
  const current = scope.previewId || scope.selectedId;
  const selectedIndex = data.x.items.findIndex((item) => item.id === current);
  const error = typeof geometry === "string" ? geometry : null;
  const g = geometry && typeof geometry !== "string" ? geometry : null;
  const empty =
    !data.x.items.length ||
    !data.series.some((s) => s.values.some((v) => v !== null));
  const itemAt = (event: {
    clientX: number;
    clientY: number;
    currentTarget: SVGSVGElement;
  }) => {
    if (!g) return null;
    const box = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - box.left) * width) / box.width,
      y = ((event.clientY - box.top) * g.height) / box.height;
    if (x < g.left || x > g.right || y < g.top || y > g.bottom) return null;
    return (
      data.x.items[nearestCategory(x, data.x.items.length, g.left, g.right)]
        ?.id || null
    );
  };
  return (
    <div ref={element} className="ed-chart-line" data-chart-geometry="line">
      {error ? (
        <ChartDiagnostic>{error}</ChartDiagnostic>
      ) : empty ? (
        <p className="ed-chart-empty">No observations to plot.</p>
      ) : (
        g && (
          <>
            <svg
              width={width}
              height={g.height}
              role="img"
              aria-labelledby={`${scope.titleId} ${id}`}
              aria-describedby={scope.summaryId}
              onPointerMove={(event) => {
                if (event.pointerType !== "touch") scope.preview(itemAt(event));
              }}
              onPointerLeave={() => scope.preview(null)}
              onPointerDown={(event) => {
                start.current = itemAt(event)
                  ? {
                      x: event.clientX,
                      y: event.clientY,
                      pointer: event.pointerId,
                    }
                  : null;
              }}
              onPointerCancel={() => {
                start.current = null;
                scope.preview(null);
              }}
              onPointerUp={(event) => {
                const down = start.current;
                start.current = null;
                const item = itemAt(event);
                if (
                  down &&
                  down.pointer === event.pointerId &&
                  Math.hypot(event.clientX - down.x, event.clientY - down.y) <
                    10 &&
                  item
                )
                  scope.inspect(item, "plot");
              }}
              data-chart-left={g.left}
              data-chart-right={g.right}
              data-chart-top={g.top}
              data-chart-bottom={g.bottom}
              data-chart-min={g.domain[0]}
              data-chart-max={g.domain[1]}
            >
              <title id={id}>
                Line chart: {data.y.label} by {data.x.label}. Inspect
                observations or open Exact data below.
              </title>
              {g.yLabel.map((line, i) => (
                <text
                  key={line.key}
                  x="0"
                  y={12 + i * 16}
                  className="ed-chart-axis-label"
                >
                  {line.text}
                </text>
              ))}
              {g.ticks.map((tick) => (
                <g key={tick.index}>
                  <text
                    x={categoryX(
                      tick.index,
                      data.x.items.length,
                      g.left,
                      g.right,
                    )}
                    y={g.bottom + 24}
                    textAnchor={
                      data.x.items.length === 1
                        ? "middle"
                        : tick.index === 0
                          ? "start"
                          : tick.index === data.x.items.length - 1
                            ? "end"
                            : "middle"
                    }
                  >
                    {tick.lines.map((line, i) => (
                      <tspan
                        key={line.key}
                        x={categoryX(
                          tick.index,
                          data.x.items.length,
                          g.left,
                          g.right,
                        )}
                        dy={i ? 16 : 0}
                      >
                        {line.text}
                      </tspan>
                    ))}
                  </text>
                </g>
              ))}
              {g.yTicks.map((value) => (
                <g key={value}>
                  <line
                    className="ed-chart-gridline"
                    x1={g.left}
                    x2={g.right}
                    y1={valueY(value, g.domain, g.top, g.bottom)}
                    y2={valueY(value, g.domain, g.top, g.bottom)}
                  />
                  <text
                    className="ed-chart-y-tick"
                    x={g.left - 8}
                    y={valueY(value, g.domain, g.top, g.bottom) + 4}
                    textAnchor="end"
                  >
                    {tickText(value)}
                  </text>
                </g>
              ))}
              {selectedIndex >= 0 && (
                <line
                  className="ed-chart-crosshair"
                  x1={categoryX(
                    selectedIndex,
                    data.x.items.length,
                    g.left,
                    g.right,
                  )}
                  x2={categoryX(
                    selectedIndex,
                    data.x.items.length,
                    g.left,
                    g.right,
                  )}
                  y1={g.top}
                  y2={g.bottom}
                />
              )}
              {data.series.map((series, seriesIndex) => (
                <g
                  key={series.id}
                  data-chart-tone={toneFor(series.tone, seriesIndex)}
                >
                  <path
                    data-chart-series={series.id}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeDasharray={dashFor(seriesIndex)}
                    d={linePath(series.values, (value, index) => ({
                      x: categoryX(index, data.x.items.length, g.left, g.right),
                      y: valueY(value, g.domain, g.top, g.bottom),
                    }))}
                  />
                  {series.values.map((value, index) =>
                    value === null ? null : (
                      <g
                        key={data.x.items[index].id}
                        data-chart-point={data.x.items[index].id}
                        data-chart-series={series.id}
                        data-chart-value={value}
                      >
                        <SeriesMark
                          index={seriesIndex}
                          x={categoryX(
                            index,
                            data.x.items.length,
                            g.left,
                            g.right,
                          )}
                          y={valueY(value, g.domain, g.top, g.bottom)}
                          selected={index === selectedIndex}
                        />
                      </g>
                    ),
                  )}
                </g>
              ))}
              {g.xLabel.map((line, i) => (
                <text
                  key={line.key}
                  className="ed-chart-axis-label"
                  x={width / 2}
                  y={g.height - 10 - (g.xLabel.length - 1 - i) * 16}
                  textAnchor="middle"
                >
                  {line.text}
                </text>
              ))}
            </svg>
            <p className="ed-chart-note ed-chart-scale">
              Scale: {String(g.domain[0])}–{String(g.domain[1])} {data.y.unit}
            </p>
          </>
        )
      )}
    </div>
  );
}
export function SegmentedBar() {
  const scope = useContext(ChartContext),
    id = useId();
  const { element, width } = useWidth();
  if (scope?.data.kind !== "parts")
    return (
      <ChartDiagnostic>
        SegmentedBar needs a ChartFrame with parts data.
      </ChartDiagnostic>
    );
  const data = scope.data,
    total = totalParts(data);
  const spans = partSpans(
    data.segments.map((s) => s.value),
    width,
  );
  return (
    <div ref={element} className="ed-chart-parts" data-chart-geometry="parts">
      {!data.segments.length ? (
        <p className="ed-chart-empty">No segments to plot.</p>
      ) : !total ? (
        <p className="ed-chart-empty">Total: 0 — no proportions to display.</p>
      ) : (
        width > 0 && (
          <svg
            width={width}
            height="44"
            role="img"
            aria-labelledby={`${scope.titleId} ${id}`}
            aria-describedby={scope.summaryId}
          >
            <title id={id}>
              Part-to-whole bar. Counts and rounded shares follow in the segment
              value list; supplied values are in Exact data.
            </title>
            {data.segments.map((segment, index) => {
              if (segment.value === 0) return null;
              const { x, width: size } = spans[index];
              return (
                <rect
                  key={segment.id}
                  data-chart-segment={segment.id}
                  data-chart-value={segment.value}
                  data-chart-tone={toneFor(segment.tone, index)}
                  x={x}
                  y="4"
                  width={size}
                  height="36"
                  fill="currentColor"
                  stroke="var(--canvas)"
                  strokeWidth="1"
                />
              );
            })}
          </svg>
        )
      )}
    </div>
  );
}
