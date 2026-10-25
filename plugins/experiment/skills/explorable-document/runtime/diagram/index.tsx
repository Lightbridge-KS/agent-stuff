import {
  type CSSProperties,
  type ReactNode,
  useContext,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import "./diagram.css";
import { DiagramContext, DiagramRoot, useEndpoint } from "./scope";

export type Tone = "neutral" | "blue" | "teal" | "orange" | "red";
type Layout =
  | { layout: "grid"; columns: 2 | 3 | 4 }
  | { layout?: "row" | "column"; columns?: never };
export type FlowProps = Layout & {
  label: string;
  description?: string;
  children: ReactNode;
  collapseBelow?: number;
  gap?: "normal" | "wide";
  className?: string;
};
export type NodeProps = {
  title: string;
  name?: string;
  subtitle?: string;
  icon?: ReactNode;
  children?: ReactNode;
  variant?: "outline" | "plain" | "filled";
  tone?: Tone;
  className?: string;
};
export type BoundaryProps = {
  title: string;
  name?: string;
  children: ReactNode;
  variant?: "outline" | "dashed" | "plain";
  tone?: Tone;
  className?: string;
};
export type ConnectorProps = {
  from: string;
  to: string;
  label?: string;
  arrows?: "end" | "both" | "none";
  line?: "solid" | "dashed";
  tone?: Tone;
};
export function Connector({
  from,
  to,
  label,
  arrows = "end",
  line = "solid",
  tone = "neutral",
}: ConnectorProps) {
  const scope = useContext(DiagramContext);
  const key = useId();
  const valid =
    typeof from === "string" &&
    from.trim() &&
    typeof to === "string" &&
    to.trim() &&
    ["end", "both", "none"].includes(arrows) &&
    ["solid", "dashed"].includes(line) &&
    tones.includes(tone) &&
    (label === undefined || typeof label === "string");
  useLayoutEffect(() => {
    if (scope && valid)
      return scope.connector(key, { from, to, label, arrows, line, tone });
  }, [scope, valid, key, from, to, label, arrows, line, tone]);
  if (!scope || !valid)
    return (
      <Diagnostic>
        Connector needs a root Flow, named from/to endpoints and valid
        arrows/line/tone.
      </Diagnostic>
    );
  return null;
}
const tones = ["neutral", "blue", "teal", "orange", "red"];
function Diagnostic({ children }: { children: ReactNode }) {
  return (
    <p className="ed-diagram-diagnostic" role="status">
      Diagram: {children}
    </p>
  );
}
export function Flow(props: FlowProps) {
  const scope = useContext(DiagramContext);
  return scope ? (
    <FlowLayout {...props} />
  ) : (
    <DiagramRoot>
      <FlowLayout {...props} />
    </DiagramRoot>
  );
}
function FlowLayout({
  label,
  description,
  children,
  layout = "row",
  columns,
  collapseBelow = 600,
  gap = "normal",
  className = "",
}: FlowProps) {
  const element = useRef<HTMLElement>(null);
  const [collapsed, setCollapsed] = useState(false);
  useLayoutEffect(() => {
    const el = element.current;
    if (!el) return;
    const update = () => setCollapsed(el.clientWidth < collapseBelow);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [collapseBelow]);
  const valid =
    typeof label === "string" &&
    label.trim() &&
    ["row", "column", "grid"].includes(layout) &&
    Number.isFinite(collapseBelow) &&
    collapseBelow > 0 &&
    (layout !== "grid" || [2, 3, 4].includes(columns || 0)) &&
    ["normal", "wide"].includes(gap);
  if (!valid)
    return (
      <Diagnostic>
        Flow needs a label, valid layout/grid columns, positive collapseBelow
        and normal/wide gap.
      </Diagnostic>
    );
  return (
    <section
      ref={element}
      className={`ed-diagram-flow ${className}`}
      aria-label={label}
    >
      {description && <p className="ed-diagram-description">{description}</p>}
      <div
        className="ed-diagram-layout"
        data-ed-layout={collapsed ? "column" : layout}
        data-ed-gap={gap}
        style={{ "--ed-columns": columns || 1 } as CSSProperties}
      >
        {children}
      </div>
    </section>
  );
}
export function Node({
  title,
  name,
  subtitle,
  icon,
  children,
  variant = "outline",
  tone = "neutral",
  className = "",
}: NodeProps) {
  const titleId = useId();
  const element = useEndpoint(name, title);
  if (
    typeof title !== "string" ||
    !title.trim() ||
    (name !== undefined && (typeof name !== "string" || !name.trim())) ||
    !tones.includes(tone) ||
    !["outline", "plain", "filled"].includes(variant)
  )
    return <Diagnostic>Node needs a title and valid tone/variant.</Diagnostic>;
  return (
    <section
      ref={element}
      className={`ed-diagram-node ${className}`}
      aria-labelledby={titleId}
      data-ed-name={name}
      data-ed-variant={variant}
      data-ed-tone={tone}
    >
      {icon && (
        <span className="ed-diagram-icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <strong id={titleId} className="ed-diagram-title">
        {title}
      </strong>
      {subtitle && <div className="ed-diagram-subtitle">{subtitle}</div>}
      {children && <div className="ed-diagram-content">{children}</div>}
    </section>
  );
}
export function Boundary({
  title,
  name,
  children,
  variant = "outline",
  tone = "neutral",
  className = "",
}: BoundaryProps) {
  const titleId = useId();
  const element = useEndpoint(name, title);
  if (
    typeof title !== "string" ||
    !title.trim() ||
    (name !== undefined && (typeof name !== "string" || !name.trim())) ||
    !tones.includes(tone) ||
    !["outline", "plain", "dashed"].includes(variant)
  )
    return (
      <Diagnostic>Boundary needs a title and valid tone/variant.</Diagnostic>
    );
  return (
    <section
      ref={element}
      className={`ed-diagram-boundary ${className}`}
      aria-labelledby={titleId}
      data-ed-name={name}
      data-ed-variant={variant}
      data-ed-tone={tone}
    >
      <strong id={titleId} className="ed-diagram-title">
        {title}
      </strong>
      <div className="ed-diagram-content">{children}</div>
    </section>
  );
}
