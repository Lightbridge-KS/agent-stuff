import type { ReactNode } from "react";
import "./recipes.css";
import {
  Boundary,
  CodePanel,
  Connector,
  Figure,
  Flow,
  Node,
} from "@explorable/kit";

function Icon({ kind = "grid" }: { kind?: string }) {
  const paths: Record<string, ReactNode> = {
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    person: (
      <>
        <circle cx="12" cy="6" r="3" />
        <path d="M5 21v-3a7 7 0 0 1 14 0v3" />
      </>
    ),
    link: (
      <>
        <path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0" />
      </>
    ),
    tree: (
      <>
        <rect x="9" y="2" width="6" height="5" rx="1" />
        <path d="M12 7v5M4 17v-5h16v5" />
        <circle cx="4" cy="20" r="2" />
        <circle cx="20" cy="20" r="2" />
        <path d="M12 12v8" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 8a9 9 0 0 0-15-3L2 8m0-6v6h6M4 16a9 9 0 0 0 15 3l3-3m0 6v-6h-6" />
      </>
    ),
    code: <path d="m7 5-6 7 6 7m10-14 6 7-6 7M14 3l-4 18" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 5v7l-4 4" />
      </>
    ),
    tool: <path d="m4 20 9-9a6 6 0 0 0 7-8l-4 4-3-3 4-4a6 6 0 0 0-8 7l-9 9z" />,
  };
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[kind] || paths.grid}
    </svg>
  );
}

export function Concepts() {
  return (
    <Figure caption="Strength, distance and volatility ask complementary questions.">
      <Flow
        label="Three dimensions of coupling"
        className="recipe-concepts"
        layout="grid"
        columns={3}
      >
        <Node
          title="Strength"
          subtitle="Knowledge"
          variant="plain"
          icon={<Icon kind="link" />}
        >
          <p>What do they know about each other?</p>
        </Node>
        <Node
          title="Distance"
          subtitle="Space"
          variant="plain"
          icon={<Icon kind="tree" />}
        >
          <p>How far apart are they?</p>
        </Node>
        <Node
          title="Volatility"
          subtitle="Time"
          variant="plain"
          icon={<Icon kind="refresh" />}
        >
          <p>How likely is their shared knowledge to change?</p>
        </Node>
      </Flow>
    </Figure>
  );
}
export function Spectrum() {
  return (
    <Figure caption="Stronger, more implicit → weaker, more explicit.">
      <Flow
        label="Integration strength spectrum"
        layout="column"
        className="recipe-spectrum"
      >
        <Node
          title="1. Intrusive coupling"
          icon={<Icon kind="link" />}
          tone="red"
          variant="filled"
        >
          <p>Knowledge of internal implementation</p>
        </Node>
        <Node
          title="2. Functional coupling"
          icon={<Icon kind="tree" />}
          tone="orange"
          variant="filled"
        >
          <p>Knowledge of business functionality and requirements</p>
        </Node>
        <Node
          title="3. Model coupling"
          icon={<Icon kind="grid" />}
          tone="blue"
          variant="filled"
        >
          <p>Knowledge of the shared domain model</p>
        </Node>
        <Node
          title="4. Contract coupling"
          icon={<Icon kind="code" />}
          tone="teal"
          variant="filled"
        >
          <p>Knowledge limited to an explicit integration contract</p>
        </Node>
      </Flow>
    </Figure>
  );
}
export function Containment() {
  return (
    <Flow label="Contained details">
      <Boundary title="Service">
        <Node title="Internal detail" />
      </Boundary>
    </Flow>
  );
}

export function Contract() {
  return (
    <>
      <CodePanel
        id="contract-code"
        title="Report service"
        language="Python"
        code={`class ReportService:
    def generate(self, result: ReportableAIResult):
        return {
            "study_uid": result.study_uid,
            "ai_conclusion": result.conclusion,
        }`}
        note="Display-only Python source. Select text for manual copying."
      />
      <Figure caption="The report depends on a published contract, not the inference service's internal model.">
        <Flow label="Service contract">
          <Boundary name="service" title="Inference service">
            <Node title="Internal model" />
          </Boundary>
          <Node
            name="contract"
            title="Published contract"
            variant="filled"
            tone="teal"
          >
            <code>PredictionResult</code>
          </Node>
          <Node
            name="report"
            title="Report service"
            subtitle="Consumes the contract"
          />
          <Connector from="service" to="contract" tone="teal" />
          <Connector from="contract" to="report" tone="teal" />
        </Flow>
      </Figure>
    </>
  );
}
export function Distance() {
  return (
    <Figure caption="The same dependency becomes harder to coordinate across organizational boundaries.">
      <Flow label="Coupling distance" layout="column" gap="wide">
        <Boundary name="short" title="One class — short distance" tone="teal">
          <Flow label="Within one team">
            <Node name="a" title="validate()" className="recipe-code-node">
              <span>Validation</span>
            </Node>
            <Node name="b" title="save()" className="recipe-code-node">
              <span>Persistence</span>
            </Node>
          </Flow>
        </Boundary>
        <Boundary
          name="long"
          title="Different services — long distance"
          tone="blue"
        >
          <Flow label="Across teams">
            <Node name="c" title="Reporting API">
              <span>Service boundary</span>
            </Node>
            <Node name="d" title="Billing API">
              <span>Service boundary</span>
            </Node>
          </Flow>
        </Boundary>
        <Connector from="a" to="b" arrows="both" tone="teal" />
        <Connector from="c" to="d" arrows="both" tone="blue" />
        <Connector
          from="short"
          to="long"
          label="Increasing architectural distance"
        />
      </Flow>
    </Figure>
  );
}
export function Workflow() {
  return (
    <Figure caption="Business rule changes can affect both services. The shared-knowledge association belongs to Check QC.">
      <Flow label="Result release workflow" layout="column" gap="wide">
        <Flow label="Release steps">
          <Node name="inference" title="Check inference" tone="blue" />
          <Node name="qc" title="Check QC" tone="blue" />
          <Node name="release" title="Release result" tone="blue" />
        </Flow>
        <Boundary
          name="knowledge"
          title="Shared workflow knowledge"
          variant="dashed"
          tone="orange"
        >
          <p>
            Business rules for inference, quality control and result release
            must remain consistent.
          </p>
        </Boundary>
        <Connector from="inference" to="qc" />
        <Connector from="qc" to="release" />
        <Connector
          from="qc"
          to="knowledge"
          arrows="none"
          line="dashed"
          tone="orange"
          label="Shared rules"
        />
      </Flow>
    </Figure>
  );
}
export function Architecture() {
  return (
    <Figure caption="Conceptual architecture: the agent coordinates UI and tool layers. Both contribute to the rendered experience; this document has no live agent connection.">
      <Flow
        label="Layered agent architecture"
        layout="column"
        gap="wide"
        className="recipe-architecture"
      >
        <Node
          name="user"
          title="User / ChatGPT conversation"
          subtitle="Natural language requests and UI interactions"
          variant="plain"
          icon={<Icon kind="person" />}
        />
        <Node
          name="agent"
          title="LLM / Agent orchestrator"
          icon={<Icon kind="tree" />}
          tone="blue"
          subtitle="Reasoning · UI composition · Tool selection"
        />
        <Flow label="Coordinated layers" layout="grid" columns={2} gap="wide">
          <Boundary name="ui" title="UI generation" tone="blue">
            <Icon />
            <p>Component specification and validation</p>
            <hr />
            <strong>Client UI runtime</strong>
            <p>Rendering, state, events</p>
          </Boundary>
          <Boundary name="tools" title="Tool execution" tone="orange">
            <Icon kind="tool" />
            <p>MCP / APIs / Functions</p>
            <hr />
            <strong>Backend services</strong>
            <p>Databases, business logic</p>
          </Boundary>
        </Flow>
        <Node
          name="output"
          title="Rendered interactive experience"
          variant="filled"
          icon={<Icon />}
          subtitle="Cards · Charts · Controls · Tool-driven updates"
        />
        <Connector from="user" to="agent" arrows="both" />
        <Connector from="agent" to="ui" tone="blue" />
        <Connector from="agent" to="tools" arrows="both" tone="orange" />
        <Connector from="ui" to="output" tone="blue" />
        <Connector from="tools" to="output" tone="orange" />
      </Flow>
    </Figure>
  );
}
