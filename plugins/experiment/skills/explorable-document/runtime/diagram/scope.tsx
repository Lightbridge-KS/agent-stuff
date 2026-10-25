import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { placeLabel, type Rect, type Route, route } from "./geometry";
import type { ConnectorProps } from "./index";

type Endpoint = { element: HTMLElement; name?: string; title: string };
type Scope = {
  endpoint: (key: string, value: Endpoint) => () => void;
  connector: (key: string, value: ConnectorProps) => () => void;
};
export const DiagramContext = createContext<Scope | null>(null);
export function useEndpoint(name: string | undefined, title: string) {
  const scope = useContext(DiagramContext);
  const element = useRef<HTMLElement>(null);
  const key = useId();
  useLayoutEffect(() => {
    if (element.current && scope)
      return scope.endpoint(key, { element: element.current, name, title });
  }, [scope, key, name, title]);
  return element;
}
type Edge = {
  key: string;
  spec: ConnectorProps;
  text: string;
  path?: Route;
  label?: Rect;
};
type View = { width: number; height: number; edges: Edge[]; issues: string[] };
const empty: View = { width: 0, height: 0, edges: [], issues: [] };
export function DiagramRoot({ children }: { children: ReactNode }) {
  const canvas = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const endpoints = useRef(new Map<string, Endpoint>());
  const connectors = useRef(new Map<string, ConnectorProps>());
  const labels = useRef(new Map<string, HTMLSpanElement>());
  const observer = useRef<ResizeObserver | null>(null);
  const schedule = useRef(() => {});
  const [view, setView] = useState<View>(empty);
  const marker = `ed-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const scope = useMemo<Scope>(
    () => ({
      endpoint(key, value) {
        endpoints.current.set(key, value);
        observer.current?.observe(value.element);
        schedule.current();
        return () => {
          observer.current?.unobserve(value.element);
          endpoints.current.delete(key);
          schedule.current();
        };
      },
      connector(key, value) {
        connectors.current.set(key, value);
        schedule.current();
        return () => {
          connectors.current.delete(key);
          schedule.current();
        };
      },
    }),
    [],
  );
  const measure = useCallback(() => {
    if (!canvas.current) return;
    const box = canvas.current.getBoundingClientRect();
    const size = { width: box.width, height: box.height };
    const bounds = (el: HTMLElement): Rect => {
      const r = el.getBoundingClientRect();
      return {
        x: r.x - box.x,
        y: r.y - box.y,
        width: r.width,
        height: r.height,
      };
    };
    const nodes = [...endpoints.current.values()];
    const byName = new Map<string, Endpoint[]>();
    const issues: string[] = [];
    for (const node of nodes) {
      if (node.name === undefined) continue;
      if (!node.name.trim()) {
        issues.push("Endpoint names must not be empty.");
        continue;
      }
      byName.set(node.name, [...(byName.get(node.name) || []), node]);
    }
    for (const [name, matches] of byName)
      if (matches.length > 1)
        issues.push(
          `Duplicate endpoint “${name}”; give each Node or Boundary a unique name in this Flow.`,
        );
    const paths: Route[] = [],
      placedLabels: Rect[] = [];
    const edges: Edge[] = [];
    for (const [key, spec] of connectors.current) {
      const { from, to, arrows = "end", label } = spec;
      const source = byName.get(from),
        target = byName.get(to);
      const a = source?.length === 1 ? source[0] : undefined;
      const b = target?.length === 1 ? target[0] : undefined;
      const relation =
        arrows === "both"
          ? "connects both ways with"
          : arrows === "none"
            ? "is associated with"
            : "connects to";
      const edge: Edge = {
        key,
        spec,
        text: `${a?.title || from} ${relation} ${b?.title || to}${label ? ` — ${label}` : ""}.`,
      };
      edges.push(edge);
      if (from === to) {
        issues.push(
          `Self-loop “${from}” is unsupported; describe it in prose.`,
        );
        continue;
      }
      if (!a || !b) {
        issues.push(
          `Cannot resolve “${from}” → “${to}”; use unique named endpoints in this root Flow.`,
        );
        continue;
      }
      const ra = bounds(a.element),
        rb = bounds(b.element);
      if (!ra.width || !ra.height || !rb.width || !rb.height || !size.width)
        continue;
      // Ancestor boundaries contain an endpoint, so must not block access to it.
      const obstacles = nodes
        .filter(
          (n) =>
            n !== a &&
            n !== b &&
            !n.element.contains(a.element) &&
            !n.element.contains(b.element),
        )
        .map((n) => bounds(n.element))
        .filter((r) => r.width && r.height);
      const path = route(ra, rb, obstacles, size, paths);
      if (!path) {
        issues.push(
          `No clear route for “${from}” → “${to}”; increase Flow gaps or simplify the layout.`,
        );
        continue;
      }
      edge.path = path;
      paths.push(path);
      if (label) {
        const labelEl = labels.current.get(key);
        const labelSize = labelEl?.getBoundingClientRect();
        if (labelSize?.width && labelSize.height) {
          edge.label =
            placeLabel(
              path,
              labelSize,
              [...nodes.map((n) => bounds(n.element)), ...placedLabels],
              size,
            ) || undefined;
          if (edge.label) placedLabels.push(edge.label);
          else
            issues.push(
              `Label for “${from}” → “${to}” does not fit; read Diagram relationships or increase the gap.`,
            );
        }
      }
    }
    const next = { ...size, edges, issues };
    setView((old) =>
      JSON.stringify(old) === JSON.stringify(next) ? old : next,
    );
  }, []);
  useLayoutEffect(() => {
    let frame = 0,
      disposed = false;
    const request = () => {
      if (!frame && !disposed)
        frame = requestAnimationFrame(() => {
          frame = 0;
          measure();
        });
    };
    schedule.current = request;
    const resize = new ResizeObserver(request);
    observer.current = resize;
    if (canvas.current) resize.observe(canvas.current);
    for (const node of endpoints.current.values()) resize.observe(node.element);
    const mutation = new MutationObserver(request);
    if (content.current)
      mutation.observe(content.current, {
        subtree: true,
        childList: true,
        characterData: true,
        attributes: true,
      });
    document.fonts.ready.then(request);
    request();
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resize.disconnect();
      mutation.disconnect();
      observer.current = null;
      schedule.current = () => {};
    };
  }, [measure]);
  // A first pass establishes label elements; a second measures their real wrapping.
  useLayoutEffect(() => {
    schedule.current();
  });
  return (
    <DiagramContext.Provider value={scope}>
      <div
        className="ed-diagram-root"
        data-ed-root=""
        data-ed-connected={!!view.edges.length}
      >
        <div ref={canvas} className="ed-diagram-canvas">
          <div ref={content}>{children}</div>
          <svg
            className="ed-diagram-overlay"
            width={view.width}
            height={view.height}
            aria-hidden="true"
          >
            <defs>
              <marker
                id={marker}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
              </marker>
            </defs>
            {view.edges
              .filter((e) => e.path)
              .map((e) => (
                <path
                  key={e.key}
                  data-ed-from={e.spec.from}
                  data-ed-to={e.spec.to}
                  data-ed-tone={e.spec.tone || "neutral"}
                  data-ed-route={e.path?.kind}
                  d={e.path?.points
                    .map((p, i) => `${i ? "L" : "M"} ${p.x} ${p.y}`)
                    .join(" ")}
                  fill="none"
                  strokeWidth="1.5"
                  strokeDasharray={e.spec.line === "dashed" ? "5 5" : undefined}
                  markerEnd={
                    e.spec.arrows === "none" ? undefined : `url(#${marker})`
                  }
                  markerStart={
                    e.spec.arrows === "both" ? `url(#${marker})` : undefined
                  }
                />
              ))}
          </svg>
          <div className="ed-diagram-labels" aria-hidden="true">
            {view.edges
              .filter((e) => e.spec.label)
              .map((e) => (
                <span
                  key={e.key}
                  ref={(el) => {
                    if (el) labels.current.set(e.key, el);
                    else labels.current.delete(e.key);
                  }}
                  className="ed-diagram-edge-label"
                  style={{
                    left: e.label?.x || 0,
                    top: e.label?.y || 0,
                    visibility: e.label ? "visible" : "hidden",
                  }}
                >
                  {e.spec.label}
                </span>
              ))}
          </div>
        </div>
        {view.issues.map((issue) => (
          <p className="ed-diagram-diagnostic" role="status" key={issue}>
            Diagram: {issue}
          </p>
        ))}
        {!!view.edges.length && (
          <details className="ed-diagram-relationships">
            <summary>Diagram relationships</summary>
            <ul>
              {view.edges.map((e) => (
                <li key={e.key}>{e.text}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </DiagramContext.Provider>
  );
}
