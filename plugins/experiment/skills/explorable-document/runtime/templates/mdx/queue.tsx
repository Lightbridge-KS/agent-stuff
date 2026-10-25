import { Figure, Range, useSnapshot } from "@explorable/kit";
import { useState } from "react";
import { queue } from "./model";
export default function Queue() {
  const [arrival, setArrival] = useState(4);
  const [service, setService] = useState(8);
  const result = queue(arrival, service);
  useSnapshot(() => ({ arrival, service, jobs: result.jobs }));
  return (
    <>
      <div className="grid">
        <Range
          label="Arrival rate"
          value={arrival}
          min={0}
          max={20}
          onChange={setArrival}
        />
        <Range
          label="Service rate"
          value={service}
          min={1}
          max={20}
          onChange={setService}
        />
      </div>
      <Figure caption="Arrivals feed the queue, which feeds the server. The dashed boundary names the shared assumption.">
        <svg
          className="flow-wide"
          viewBox="0 0 640 170"
          role="img"
          aria-label="Arrivals flow through a queue to a server; one shared steady-state model"
        >
          <title>Queue flow</title>
          <defs>
            <marker
              id="arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--blue)" />
            </marker>
          </defs>
          {[
            { x: 0, label: "Arrivals" },
            { x: 240, label: "Queue" },
            { x: 480, label: "Server" },
          ].map((node) => (
            <g key={node.label}>
              <rect
                x={node.x + 1}
                y="5"
                width="158"
                height="60"
                rx="12"
                fill="var(--raised)"
                stroke="var(--blue)"
              />
              <text
                x={node.x + 80}
                y="42"
                textAnchor="middle"
                fill="var(--text)"
                fontSize="22"
              >
                {node.label}
              </text>
            </g>
          ))}
          <path
            d="M160 35 H230"
            stroke="var(--blue)"
            strokeWidth="2"
            markerEnd="url(#arrow)"
          />
          <path
            d="M400 35 H470"
            stroke="var(--blue)"
            strokeWidth="2"
            markerEnd="url(#arrow)"
          />
          <rect
            x="1"
            y="95"
            width="638"
            height="60"
            rx="12"
            fill="none"
            stroke="var(--orange)"
            strokeDasharray="6 5"
          />
          <text
            x="320"
            y="132"
            textAnchor="middle"
            fill="var(--orange)"
            fontSize="21"
          >
            One server · steady-state assumptions
          </text>
        </svg>
        <svg
          className="flow-narrow"
          viewBox="0 0 260 365"
          role="img"
          aria-label="Arrivals flow down through a queue to a server. One server, steady-state assumptions."
        >
          <title>Queue flow on narrow screens</title>
          <defs>
            <marker
              id="arrow-down"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--blue)" />
            </marker>
          </defs>
          {[
            { y: 5, label: "Arrivals" },
            { y: 95, label: "Queue" },
            { y: 185, label: "Server" },
          ].map((node) => (
            <g key={node.label}>
              <rect
                x="45"
                y={node.y}
                width="170"
                height="56"
                rx="12"
                fill="var(--raised)"
                stroke="var(--blue)"
              />
              <text
                x="130"
                y={node.y + 35}
                textAnchor="middle"
                fill="var(--text)"
                fontSize="21"
              >
                {node.label}
              </text>
            </g>
          ))}
          <path
            d="M130 61 V85"
            stroke="var(--blue)"
            strokeWidth="2"
            markerEnd="url(#arrow-down)"
          />
          <path
            d="M130 151 V175"
            stroke="var(--blue)"
            strokeWidth="2"
            markerEnd="url(#arrow-down)"
          />
          <rect
            x="1"
            y="270"
            width="258"
            height="80"
            rx="12"
            fill="none"
            stroke="var(--orange)"
            strokeDasharray="6 5"
          />
          <text
            x="130"
            y="302"
            textAnchor="middle"
            fill="var(--orange)"
            fontSize="18"
          >
            One server
            <tspan x="130" dy="26">
              Steady-state assumptions
            </tspan>
          </text>
        </svg>
        <p id="queue-diagram">
          Utilization: {(result.utilization * 100).toFixed(0)}%
        </p>
        <div
          style={{ height: 12, background: "var(--raised)", borderRadius: 6 }}
        >
          <div
            style={{
              height: 12,
              width: `${Math.min(100, result.utilization * 100)}%`,
              background: "var(--blue)",
              borderRadius: 6,
            }}
          />
        </div>
      </Figure>
      <p id="scenario-summary" aria-live="polite">
        {result.jobs === null
          ? "Overloaded: no finite steady-state queue."
          : `Mean jobs in system: ${result.jobs.toFixed(2)}.`}
      </p>
      <button
        type="button"
        onClick={() => {
          setArrival(4);
          setService(8);
        }}
      >
        Reset scenario
      </button>
    </>
  );
}
