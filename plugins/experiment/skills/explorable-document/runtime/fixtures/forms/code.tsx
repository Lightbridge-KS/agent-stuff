import {
  CodePanel,
  type CodePanelProps,
  type JsonValue,
  NumberField,
} from "@explorable/kit";
import { useState } from "react";
export default function Code() {
  const [draft, setDraft] = useState("1");
  const [mode, setMode] = useState("normal"),
    [wrap, setWrap] = useState(true);
  const cycle: Record<string, unknown> = {};
  cycle.self = cycle;
  const value =
    mode === "invalid"
      ? cycle
      : mode === "null"
        ? null
        : { draft, literal: "<b>not markup</b>" };
  const badProps =
    mode === "both"
      ? { code: "a", value: null }
      : { value: value as JsonValue };
  return (
    <>
      <h1>Code panel fixtures</h1>
      <NumberField id="draft" label="Draft" value={draft} onChange={setDraft} />
      <label htmlFor="mode">Fixture mode</label>
      <select id="mode" value={mode} onChange={(e) => setMode(e.target.value)}>
        {["normal", "invalid", "null", "empty", "both"].map((v) => (
          <option key={v}>{v}</option>
        ))}
      </select>
      <label>
        <input
          id="wrap"
          type="checkbox"
          checked={wrap}
          onChange={(e) => setWrap(e.target.checked)}
        />
        Wrap source
      </label>
      <CodePanel
        {...({
          ...badProps,
          id: "first-code",
          title: "Live JSON",
        } as CodePanelProps)}
      />
      <CodePanel
        id="second-code"
        title="Source"
        code={
          mode === "empty"
            ? ""
            : `line one\r\n${"long_source_<b>literal</b>_".repeat(30)}`
        }
        wrap={wrap}
      />
    </>
  );
}
