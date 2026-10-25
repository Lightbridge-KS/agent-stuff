import { Figure } from "@explorable/kit";
import { useState } from "react";

const steps = [
  {
    title: "Author",
    detail: "Write the explanation and declare useful interactions.",
  },
  {
    title: "Build",
    detail: "Compile the fixed source and check its contracts.",
  },
  {
    title: "Explore",
    detail: "Use local controls to examine the explanation.",
  },
  {
    title: "Review",
    detail: "Optionally review a frozen snapshot before sharing.",
  },
];
export default function Walkthrough() {
  const [step, setStep] = useState(0);
  return (
    <>
      <h1>From explanation to exploration</h1>
      <p>
        Each step has a different responsibility. Move through them in order or
        reset to the beginning.
      </p>
      <Figure caption="The active step is numbered and labeled, independently of color.">
        <ol className="grid">
          {steps.map((item, index) => (
            <li
              key={item.title}
              className="node"
              aria-current={step === index ? "step" : undefined}
            >
              <strong>{item.title}</strong>
              {step === index && <p>Current step</p>}
            </li>
          ))}
        </ol>
      </Figure>
      <h2 id="step-title">
        {step + 1}. {steps[step].title}
      </h2>
      <p id="step-detail" aria-live="polite">
        {steps[step].detail}
      </p>
      <div className="actions">
        <button
          type="button"
          disabled={step === 0}
          onClick={() => setStep(step - 1)}
        >
          Back
        </button>
        <button
          type="button"
          disabled={step === steps.length - 1}
          onClick={() => setStep(step + 1)}
        >
          Next
        </button>
        <button type="button" onClick={() => setStep(0)}>
          Reset
        </button>
      </div>
    </>
  );
}
