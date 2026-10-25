import {
  isValidElement,
  type ReactElement,
  type ReactNode,
  useEffect,
  useId,
  useState,
} from "react";
import { ChartContext, type SelectionChange } from "./context";
import {
  type ChartData,
  type ChartTone,
  displayValue,
  exactValue,
  type PartsData,
  shareText,
  toneFor,
  totalParts,
  validateData,
  type XYData,
} from "./model";
import "./chart.css";
import { dashFor, SeriesMark } from "./marks";

export type { ChartData, ChartTone, PartsData, SelectionChange, XYData };

type Selection =
  | {
      selectedId: string | null;
      onSelectionChange: (change: SelectionChange) => void;
      defaultSelectedId?: never;
    }
  | {
      selectedId?: never;
      onSelectionChange?: never;
      defaultSelectedId?: string;
    };
type Common = {
  title: string;
  summary: string;
  children: ReactElement;
  controls?: ReactNode;
  note?: string;
  className?: string;
};
export type ChartFrameProps = Common &
  (
    | ({ data: XYData } & Selection)
    | {
        data: PartsData;
        selectedId?: never;
        onSelectionChange?: never;
        defaultSelectedId?: never;
      }
  );
export function ChartDiagnostic({ children }: { children: ReactNode }) {
  return (
    <p className="ed-chart-diagnostic" role="status">
      Chart: {children}
    </p>
  );
}
function Legend({ data }: { data: ChartData }) {
  if (data.kind === "xy")
    return (
      <ul className="ed-chart-legend" aria-label="Series">
        {data.series.map((series, index) => (
          <li key={series.id}>
            <svg
              width="38"
              height="20"
              aria-hidden="true"
              data-chart-tone={toneFor(series.tone, index)}
            >
              <path
                d="M 0 10 H 38"
                stroke="currentColor"
                strokeWidth="2"
                strokeDasharray={dashFor(index)}
              />
              <SeriesMark index={index} x={19} y={10} />
            </svg>
            <span>{series.label}</span>
          </li>
        ))}
      </ul>
    );
  const total = totalParts(data);
  return (
    <>
      <p className="ed-chart-note">Counts ({data.unit}) · rounded shares</p>
      <ul
        className="ed-chart-parts-list"
        aria-label={`Segment counts (${data.unit}) and rounded shares`}
      >
        {data.segments.map((s, index) => (
          <li key={s.id}>
            <span>
              <span
                className="ed-chart-swatch"
                data-chart-tone={toneFor(s.tone, index)}
                aria-hidden="true"
              />
              {s.label}
            </span>
            <span>{displayValue(s.value)}</span>
            <span>{total ? shareText(s.value, total) : "Unavailable"}</span>
          </li>
        ))}
      </ul>
      <p className="ed-chart-total">
        Total: {displayValue(total)} {data.unit}
      </p>
      {!!total && <p className="ed-chart-note">Percentages are rounded.</p>}
    </>
  );
}
function ExactTable({
  data,
  title,
  id,
}: {
  data: ChartData;
  title: string;
  id: string;
}) {
  return (
    <details className="ed-chart-data" id={id}>
      <summary>Exact data</summary>
      <table>
        <caption>
          {title} — supplied values (
          {data.kind === "xy" ? data.y.unit : data.unit})
        </caption>
        {data.kind === "xy" ? (
          <>
            <thead>
              <tr>
                <th scope="col">{data.x.label}</th>
                {data.series.map((s) => (
                  <th scope="col" key={s.id}>
                    {s.label} ({data.y.unit})
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.x.items.map((item, index) => (
                <tr key={item.id}>
                  <th scope="row">{item.label}</th>
                  {data.series.map((s) => (
                    <td key={s.id}>{exactValue(s.values[index])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </>
        ) : (
          <>
            <thead>
              <tr>
                <th scope="col">Segment</th>
                <th scope="col">Count ({data.unit})</th>
              </tr>
            </thead>
            <tbody>
              {data.segments.map((s) => (
                <tr key={s.id}>
                  <th scope="row">{s.label}</th>
                  <td>{exactValue(s.value)}</td>
                </tr>
              ))}
            </tbody>
          </>
        )}
      </table>
    </details>
  );
}
function reading(data: XYData, id: string | null): string {
  const index = data.x.items.findIndex((item) => item.id === id);
  if (index < 0) return "Choose an observation to inspect.";
  return `${data.x.items[index].label} · ${data.series.map((s) => `${s.label}: ${displayValue(s.values[index])}${s.values[index] === null ? "" : ` ${data.y.unit}`}`).join(" · ")}`;
}
export function ChartFrame(props: ChartFrameProps) {
  const { title, summary, children, controls, note, className = "" } = props;
  const id = useId();
  const validation = validateData(props.data);
  const data = validation ? null : props.data;
  const items = data?.kind === "xy" ? data.x.items : [];
  const controlled = props.selectedId !== undefined;
  const [selection, setSelection] = useState<string | null>(
    () => props.defaultSelectedId || items[0]?.id || null,
  );
  const [hover, setHover] = useState<{ key: string; id: string } | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const key = JSON.stringify(data);
  const selected = controlled
    ? (props.selectedId ?? null)
    : items.some((i) => i.id === selection)
      ? selection
      : items[0]?.id || null;
  const preview =
    hover?.key === key && items.some((i) => i.id === hover.id)
      ? hover.id
      : null;
  useEffect(() => {
    if (data && !controlled && selected !== selection) setSelection(selected);
  }, [data, controlled, selected, selection]);
  useEffect(() => {
    void key;
    setHover(null);
  }, [key]);
  let issue = validation;
  if (
    typeof title !== "string" ||
    !title.trim() ||
    typeof summary !== "string" ||
    !summary.trim()
  )
    issue = "Supply a nonempty title and meaningful summary.";
  if (!isValidElement(children))
    issue = "Supply one plot element as the frame child.";
  if (
    data?.kind === "parts" &&
    (props.selectedId !== undefined ||
      props.onSelectionChange !== undefined ||
      props.defaultSelectedId !== undefined)
  )
    issue = "Parts charts do not have selection props.";
  if (data?.kind === "xy") {
    if (
      controlled !== (typeof props.onSelectionChange === "function") ||
      (controlled && props.defaultSelectedId !== undefined)
    )
      issue =
        "Supply selectedId and onSelectionChange together, or defaultSelectedId for an uncontrolled chart.";
    if (
      controlled &&
      selected !== null &&
      !items.some((item) => item.id === selected)
    )
      issue = `Selected category “${selected}” is not in this dataset; update the controlled selection.`;
  }
  if (
    props.defaultSelectedId !== undefined &&
    (typeof props.defaultSelectedId !== "string" ||
      !props.defaultSelectedId.trim())
  )
    issue = "defaultSelectedId must be a nonempty category ID.";
  if (
    props.selectedId !== undefined &&
    props.selectedId !== null &&
    typeof props.selectedId !== "string"
  )
    issue = "selectedId must be a category ID or null.";
  const inspect = (item: string, source: SelectionChange["source"]) => {
    if (data?.kind !== "xy" || !items.some((i) => i.id === item)) return;
    setHover(null);
    if (controlled) props.onSelectionChange?.({ id: item, source });
    else setSelection(item);
    setAnnouncement(reading(data, item));
  };
  const index = items.findIndex((i) => i.id === selected);
  return (
    <figure
      className={`figure ed-chart-frame ${className}`}
      aria-labelledby={`${id}-title`}
    >
      <figcaption className="ed-chart-header">
        <strong id={`${id}-title`}>
          {typeof title === "string" ? title : "Chart"}
        </strong>
        {controls && <div className="ed-chart-controls">{controls}</div>}
      </figcaption>
      <p className="ed-chart-summary" id={`${id}-summary`}>
        {typeof summary === "string" ? summary : ""}
      </p>
      {issue ? (
        <ChartDiagnostic>{issue}</ChartDiagnostic>
      ) : (
        data && (
          <ChartContext.Provider
            value={{
              data,
              titleId: `${id}-title`,
              summaryId: `${id}-summary`,
              tableId: `${id}-table`,
              selectedId: selected,
              previewId: preview,
              inspect,
              preview: (item) => setHover(item ? { key, id: item } : null),
            }}
          >
            <div className="ed-chart-plot">{children}</div>
            <Legend data={data} />
            {data.kind === "xy" && (
              <>
                <div className="ed-chart-inspect">
                  <label htmlFor={`${id}-inspect`}>
                    Inspect {data.x.label}
                    <select
                      id={`${id}-inspect`}
                      value={selected || ""}
                      disabled={!items.length}
                      onChange={(e) => inspect(e.target.value, "control")}
                    >
                      <option value="" disabled>
                        Choose an observation
                      </option>
                      {items.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="ed-chart-navigation">
                    <button
                      type="button"
                      disabled={index <= 0}
                      onClick={() => inspect(items[index - 1].id, "control")}
                    >
                      Previous
                    </button>
                    <button
                      type="button"
                      disabled={index < 0 || index >= items.length - 1}
                      onClick={() => inspect(items[index + 1].id, "control")}
                    >
                      Next
                    </button>
                  </div>
                </div>
                <div className="ed-chart-readout" aria-live="off">
                  {preview ? "Preview" : "Selected"} ·{" "}
                  {reading(data, preview || selected)}
                </div>
              </>
            )}
            <ExactTable data={data} title={title} id={`${id}-table`} />
          </ChartContext.Provider>
        )
      )}
      {note && <p className="ed-chart-note">{note}</p>}
      <p className="ed-chart-sr" role="status">
        {announcement}
      </p>
    </figure>
  );
}

export type { LinePlotProps } from "./plots";
export { LinePlot, SegmentedBar } from "./plots";
