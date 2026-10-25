import { type ReactNode, useEffect, useId } from "react";
import { registerSnapshot } from "./bridge";

export function Document({ children }: { children: ReactNode }) {
  return <article className="document">{children}</article>;
}
export function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}
export function Figure({
  caption,
  children,
}: {
  caption: string;
  children: ReactNode;
}) {
  return (
    <figure className="figure">
      {children}
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
export function ExplorePanel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section className="panel" aria-labelledby={id}>
      <h3 id={id}>{title}</h3>
      {children}
    </section>
  );
}
/** Register the current render's provider; values never leave on state change. */
export function useSnapshot(provider: () => unknown): void {
  useEffect(() => registerSnapshot(provider), [provider]);
}

export type {
  ChartData,
  ChartFrameProps,
  ChartTone,
  LinePlotProps,
  PartsData,
  SelectionChange,
  XYData,
} from "./chart";
export { ChartFrame, LinePlot, SegmentedBar } from "./chart";
export type { CodePanelProps, JsonValue } from "./code";
export { CodePanel } from "./code";
export type {
  BoundaryProps,
  ConnectorProps,
  FlowProps,
  NodeProps,
  Tone,
} from "./diagram";
export { Boundary, Connector, Flow, Node } from "./diagram";
export type {
  CheckboxFieldProps,
  FieldOption,
  FieldProps,
  NumberFieldProps,
  NumberReading,
  NumberRules,
  RadioGroupProps,
  RadioOption,
  RangeProps,
  SelectFieldProps,
} from "./form";
export {
  CheckboxField,
  NumberField,
  RadioGroup,
  Range,
  readNumber,
  SelectField,
} from "./form";
