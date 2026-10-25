import { useEffect, useId, useRef, useState } from "react";
import { type JsonValue, panelText } from "./text";
import "./code.css";

export type { JsonValue } from "./text";

interface PanelProps {
  title: string;
  id?: string;
  note?: string;
  wrap?: boolean;
  className?: string;
  emptyMessage?: string;
}
export type CodePanelProps = PanelProps &
  (
    | { code: string; value?: never; language?: string }
    | { value: JsonValue; code?: never; language?: never }
  );
export function CodePanel(props: CodePanelProps) {
  const generated = useId();
  const id = props.id ?? `ed-code-${generated}`;
  const ref = useRef<HTMLTextAreaElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const derived = panelText(props);
  const propError =
    typeof props.title !== "string" || !props.title.trim()
      ? "A nonempty title is required."
      : props.id !== undefined &&
          (typeof props.id !== "string" ||
            !props.id.trim() ||
            /\s/.test(props.id))
        ? "id must be nonempty without whitespace."
        : [props.note, props.className, props.emptyMessage].some(
              (v) => v !== undefined && typeof v !== "string",
            )
          ? "note, className and emptyMessage must be text."
          : props.wrap !== undefined && typeof props.wrap !== "boolean"
            ? "wrap must be boolean."
            : null;
  const error = propError || derived.error;
  const text = error ? "" : derived.text;
  const ready = !error && text.length > 0;
  useEffect(() => {
    setSelected((previous) => (previous === text ? previous : null));
  }, [text]);
  return (
    <section
      id={id}
      className={`ed-code-panel ${typeof props.className === "string" ? props.className : ""}`}
      aria-labelledby={`${id}-title`}
    >
      <div className="ed-code-header">
        <strong id={`${id}-title`}>
          {typeof props.title === "string" && props.title.trim()
            ? props.title
            : "Code panel"}
        </strong>
        <span className="ed-code-format">{derived.format} · Read only</span>
        <button
          id={`${id}-select`}
          type="button"
          disabled={!ready}
          onClick={() => {
            if (!ref.current) return;
            ref.current.focus();
            ref.current.select();
            setSelected(text);
          }}
        >
          Select text
        </button>
      </div>
      {error && (
        <p className="ed-code-error" id={`${id}-error`}>
          Code panel unavailable: {error}
        </p>
      )}
      <textarea
        ref={ref}
        id={`${id}-text`}
        aria-labelledby={`${id}-title`}
        aria-describedby={[`${id}-help`, error && `${id}-error`]
          .filter(Boolean)
          .join(" ")}
        readOnly
        spellCheck={false}
        value={text}
        rows={Math.min(16, Math.max(4, text.split("\n").length))}
        wrap={props.wrap === false ? "off" : "soft"}
        placeholder={
          error
            ? "Preview unavailable"
            : props.emptyMessage || "No text to display"
        }
        onBlur={() => setSelected(null)}
      />
      <p className="ed-code-help" id={`${id}-help`}>
        {typeof props.note === "string"
          ? props.note
          : "Select the text, then use the system copy shortcut or text menu."}
      </p>
      <p className="ed-code-status" id={`${id}-status`} role="status">
        {ready && selected === text
          ? "Text selected. Use your system copy shortcut."
          : ""}
      </p>
    </section>
  );
}
