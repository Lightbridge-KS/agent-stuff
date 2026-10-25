import { NumberField, readNumber } from "@explorable/kit";
import { useState } from "react";
export default function Numeric() {
  const [tp, setTp] = useState("85"),
    [fn, setFn] = useState("15"),
    [optional, setOptional] = useState("");
  const [domain, setDomain] = useState(false);
  const rules = { integer: true, min: 0, max: 1000000, required: true };
  const a = readNumber(tp, rules),
    b = readNumber(fn, rules);
  const valid = a.status === "valid" && b.status === "valid";
  const ratio =
    valid && a.value + b.value > 0
      ? (100 * a.value) / (a.value + b.value)
      : null;
  return (
    <>
      <h1>Numeric drafts</h1>
      <form id="numeric-form" onSubmit={(e) => e.preventDefault()}>
        <NumberField
          id="tp"
          label="True positive"
          help="Whole count from 0 to 1,000,000."
          {...rules}
          value={tp}
          onChange={setTp}
          error={domain ? "Domain error" : undefined}
        />
        <NumberField
          id="fn"
          label="False negative"
          {...rules}
          value={fn}
          onChange={setFn}
          validation="change"
        />
        <NumberField
          id="optional"
          label="Optional decimal"
          value={optional}
          onChange={setOptional}
        />
        <button
          id="reset"
          type="button"
          onClick={() => {
            setTp("85");
            setFn("15");
            setOptional("");
            setDomain(false);
          }}
        >
          Reset counts
        </button>
        <button id="domain" type="button" onClick={() => setDomain((v) => !v)}>
          Toggle domain error
        </button>
        <button type="submit">Validate form</button>
      </form>
      <output id="ratio">
        {valid
          ? ratio === null
            ? "Undefined"
            : `${ratio.toFixed(1)}%`
          : "Waiting"}
      </output>
    </>
  );
}
