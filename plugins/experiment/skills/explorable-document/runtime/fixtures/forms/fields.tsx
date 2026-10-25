import { CheckboxField, RadioGroup, Range, SelectField } from "@explorable/kit";
import { useState } from "react";

const options = [
  { value: "a", label: "Alpha", description: "First option" },
  { value: "b", label: "Beta" },
];
export default function Fields() {
  const [first, setFirst] = useState<string | null>(null);
  const [second, setSecond] = useState<string | null>("a");
  const [chosen, setChosen] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const [range, setRange] = useState(4);
  const [mode, setMode] = useState("normal");
  const [callbacks, setCallbacks] = useState(0);
  const choices =
    mode === "duplicate"
      ? [options[0], options[0]]
      : mode === "empty"
        ? []
        : mode === "disabled"
          ? options.map((o) => ({ ...o, disabled: o.value === "b" }))
          : options;
  return (
    <>
      <h1>Field acceptance fixture</h1>
      <label htmlFor="mode">Fixture mode</label>
      <select id="mode" value={mode} onChange={(e) => setMode(e.target.value)}>
        {["normal", "disabled", "empty", "duplicate", "error"].map((m) => (
          <option key={m}>{m}</option>
        ))}
      </select>
      <form onSubmit={(e) => e.preventDefault()}>
        <RadioGroup
          id="first"
          label="First group"
          value={first}
          options={choices}
          required
          help="Choose one."
          error={mode === "error" ? "Domain rejection" : undefined}
          onChange={(v) => {
            setFirst(v);
            setCallbacks((n) => n + 1);
          }}
          layout="row"
        />
        <RadioGroup
          id="second"
          label="Second group"
          value={second}
          options={options}
          onChange={setSecond}
        />
        <SelectField
          id="choice"
          label="Choice"
          options={choices}
          value={chosen}
          onChange={setChosen}
          help="Optional choice."
        />
        <SelectField
          id="required-choice"
          label="Required choice"
          options={options}
          value={chosen}
          onChange={setChosen}
          required
        />
        <SelectField
          id="fixed"
          label="Fixed choice"
          options={options}
          value="b"
          onChange={() => {}}
          disabled
          help="Value retained."
        />
        <CheckboxField
          id="check"
          label="Consent"
          checked={checked}
          onChange={setChecked}
          required
          help="A sample checkbox."
        />
        <Range
          id="range"
          label="Rate"
          value={range}
          min={0}
          max={10}
          onChange={setRange}
          help="Jobs per minute."
        />
        <button
          id="reset"
          type="button"
          onClick={() => {
            setFirst(null);
            setSecond("a");
            setChosen(null);
            setChecked(false);
            setRange(4);
          }}
        >
          Reset values
        </button>
      </form>
      <output id="reading" style={{ overflowWrap: "anywhere" }}>
        {JSON.stringify({ first, second, chosen, checked, range, callbacks })}
      </output>
    </>
  );
}
