import { Boundary, Connector, Flow, Node } from "@explorable/kit";
import { useState } from "react";
export default function Lifecycle() {
  const [mode, setMode] = useState("normal");
  const [expanded, setExpanded] = useState(false);
  const [value, setValue] = useState("");
  return (
    <>
      <label>
        Fixture mode{" "}
        <select
          id="mode"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          {[
            "normal",
            "duplicate",
            "missing",
            "removed",
            "self",
            "hidden",
            "label",
          ].map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
      </label>
      <button type="button" id="expand" onClick={() => setExpanded(!expanded)}>
        Expand detail
      </button>
      <Flow label="Lifecycle and controls" layout="column" gap="wide">
        <Node
          name="a"
          title="A long source title that wraps naturally across multiple lines"
        >
          <label>
            Note{" "}
            <input
              id="note"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </label>
          {expanded && (
            <p>
              {"More detail expands the node while preserving the input. ".repeat(
                12,
              )}
            </p>
          )}
        </Node>
        {mode === "duplicate" && <Node name="a" title="Duplicate" />}
        {mode !== "removed" && (
          <div style={{ display: mode === "hidden" ? "none" : undefined }}>
            <Boundary title="Nested boundary">
              <Node name="b" title="Target" />
            </Boundary>
          </div>
        )}
        <Connector
          from="a"
          to={mode === "self" ? "a" : mode === "missing" ? "unknown" : "b"}
          label={
            mode === "label"
              ? "An unplaceable label. ".repeat(100)
              : "A long relationship label that wraps"
          }
        />
      </Flow>
      <Flow label="Independent scope">
        <Node name="a" title="Other source" />
        <Node name="b" title="Other target" />
        <Connector from="a" to="b" />
      </Flow>
    </>
  );
}
