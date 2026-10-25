import {
  CheckboxField,
  CodePanel,
  NumberField,
  RadioGroup,
  Range,
  readNumber,
  SelectField,
} from "@explorable/kit";
import { useState } from "react";
import "./examples.css";
export const defaults = {
  provider: "OpenAI",
  agent_mode: "tool",
  temperature: 0.3,
  max_tokens: 4096,
  tools_enabled: true,
  streaming: true,
};
export type Configuration = typeof defaults;
export function SettingsControls({
  config,
  setConfig,
}: {
  config: Configuration;
  setConfig: (config: Configuration) => void;
}) {
  return (
    <>
      <div className="settings-layout">
        <div className="example-fields">
          <RadioGroup
            id="provider"
            label="Model provider"
            value={config.provider}
            options={["OpenAI", "Anthropic", "Google"].map((value) => ({
              value,
              label: value,
            }))}
            layout="row"
            help="Choose one illustrative provider."
            onChange={(provider) => setConfig({ ...config, provider })}
          />
          <RadioGroup
            id="behavior"
            label="Agent behavior"
            value={config.agent_mode}
            options={[
              { value: "chat", label: "Chat assistant" },
              { value: "tool", label: "Tool-calling agent" },
              { value: "workflow", label: "Workflow orchestrator" },
            ]}
            onChange={(agent_mode) => setConfig({ ...config, agent_mode })}
          />
          <Range
            id="temperature"
            label="Temperature"
            value={config.temperature}
            min={0}
            max={2}
            step={0.1}
            help="A bounded numeric choice, from 0 to 2."
            onChange={(temperature) => setConfig({ ...config, temperature })}
          />
          <SelectField
            id="tokens"
            label="Max output tokens"
            value={String(config.max_tokens)}
            required
            options={[1024, 2048, 4096, 8192].map((v) => ({
              value: String(v),
              label: v.toLocaleString("en-US"),
            }))}
            help="Select one allowed limit."
            onChange={(value) => {
              if (value !== null)
                setConfig({ ...config, max_tokens: Number(value) });
            }}
          />
          <CheckboxField
            id="tools"
            label="Enable tool calling"
            checked={config.tools_enabled}
            onChange={(tools_enabled) =>
              setConfig({ ...config, tools_enabled })
            }
          />
          <CheckboxField
            id="streaming"
            label="Enable streaming output"
            checked={config.streaming}
            onChange={(streaming) => setConfig({ ...config, streaming })}
          />
          <button
            id="reset-settings"
            type="button"
            onClick={() => setConfig(defaults)}
          >
            Reset example
          </button>
        </div>
        <CodePanel
          id="configuration"
          title="Live configuration"
          value={config}
        />
      </div>
      <p id="settings-reading" className="reading">
        {config.provider} · {config.agent_mode} ·{" "}
        {config.temperature.toFixed(1)} · {config.max_tokens} · tools{" "}
        {config.tools_enabled ? "on" : "off"} · streaming{" "}
        {config.streaming ? "on" : "off"}
      </p>
    </>
  );
}
export function Settings() {
  const [config, setConfig] = useState(defaults);
  return (
    <section id="settings">
      <p className="eyebrow">A · SETTINGS AND LIVE JSON</p>
      <h2>One configuration drives the preview</h2>
      <p className="muted">
        Explore the choices locally. These settings do not configure a real
        agent.
      </p>
      <SettingsControls config={config} setConfig={setConfig} />
    </section>
  );
}
export function Counts() {
  const [tp, setTp] = useState("85"),
    [fn, setFn] = useState("15");
  const rules = { min: 0, max: 1000000, integer: true, required: true };
  const positive = readNumber(tp, rules),
    negative = readNumber(fn, rules);
  const valid = positive.status === "valid" && negative.status === "valid";
  const total = valid ? positive.value + negative.value : null;
  const result = valid
    ? total
      ? `${((100 * positive.value) / total).toFixed(1)}%`
      : "Undefined · denominator is zero"
    : positive.status === "invalid" || negative.status === "invalid"
      ? "Check the counts"
      : "Waiting for complete values";
  const preview = valid
    ? {
        value: {
          true_positive: positive.value,
          false_negative: negative.value,
          sensitivity: total ? positive.value / total : null,
        },
      }
    : { code: "", language: "JSON" };
  return (
    <section id="counts">
      <p className="eyebrow">B · NUMERIC DRAFTS AND VALIDATION</p>
      <h2>A blank is not a zero</h2>
      <p className="muted">
        Clear a count, try <code>-</code> or <code>1e</code>, then leave the
        field. The text stays visible while the calculation waits. This is
        illustrative arithmetic.
      </p>
      <div className="example-fields">
        <div className="count-grid">
          <NumberField
            id="tp"
            label="True positive"
            value={tp}
            onChange={setTp}
            {...rules}
            help="Whole count from 0 to 1,000,000."
          />
          <NumberField
            id="fn"
            label="False negative"
            value={fn}
            onChange={setFn}
            {...rules}
            help="Whole count from 0 to 1,000,000."
          />
        </div>
        <SelectField
          id="fixed-source"
          label="Data source"
          value="synthetic"
          options={[{ value: "synthetic", label: "Illustrative sample" }]}
          disabled
          onChange={() => {}}
          help="Fixed in this example; the selected value is retained."
        />
        <div className="example-result">
          <span>Sensitivity</span>
          <strong id="calculation">{result}</strong>
        </div>
        <button
          id="reset-counts"
          type="button"
          onClick={() => {
            setTp("85");
            setFn("15");
          }}
        >
          Reset counts
        </button>
      </div>
      <CodePanel
        id="calculated"
        title="Derived JSON"
        {...preview}
        emptyMessage="Complete the numeric fields to preview JSON."
        note={
          valid
            ? "A null sensitivity explicitly represents an undefined ratio when both counts are zero."
            : "Preview paused until both counts are complete and valid."
        }
      />
    </section>
  );
}
const python = `class ReportService:
    def generate(self, result):
        return {
            "study_id": result.study_id,
            "conclusion": result.conclusion,
        }`;
export function SourceCode() {
  const [wrap, setWrap] = useState(true),
    [sample, setSample] = useState("python");
  const text =
    sample === "python"
      ? python
      : `const message = "<b>Literal text, not HTML</b>: ${"A long example line stays selectable without inserting new line characters. ".repeat(5)}";`;
  return (
    <section id="source-code">
      <p className="eyebrow">C · SOURCE TEXT AND SELECTION</p>
      <h2>Readable source with a deliberate action</h2>
      <p className="muted">
        Select text highlights the source for the system copy shortcut. This
        panel displays source without executing it.
      </p>
      <div className="source-options">
        <SelectField
          id="source-sample"
          label="Sample"
          value={sample}
          options={[
            { value: "python", label: "Python example" },
            { value: "long", label: "Long line with literal markup" },
          ]}
          required
          onChange={(value) => {
            if (value !== null) setSample(value);
          }}
        />
        <CheckboxField
          id="wrap-code"
          label="Wrap code lines"
          checked={wrap}
          onChange={setWrap}
        />
      </div>
      <CodePanel
        id="python"
        title="Report service sample"
        code={text}
        language={sample === "python" ? "Python" : "Text"}
        wrap={wrap}
        note="Display only. The language label is metadata; source uses plain monospace text."
      />
    </section>
  );
}
export function Examples() {
  return (
    <>
      <Settings />
      <Counts />
      <SourceCode />
    </>
  );
}
export default function FormExamples() {
  return (
    <>
      <h1>Form and code utilities</h1>
      <Examples />
    </>
  );
}
