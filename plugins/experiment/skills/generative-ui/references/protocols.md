# Generative UI protocol landscape

`verified: 2026-06` (from talks given June–July 2026). Versions move monthly: **fetch current
docs (context7 / official repos) before quoting a version, API or default.**

| protocol | connects | owner | one-liner | tier |
|---|---|---|---|---|
| MCP | agent ↔ tools, context | Anthropic / MCP community | tool calling, resources, auth | (transport) |
| MCP Apps | UI over MCP | official MCP extension (Ido Salomon et al.); successor of MCP-UI · https://modelcontextprotocol.io/extensions/apps/overview.md | a tool ships HTML, the host renders it in a sandboxed (double) iframe; UI↔host messaging; the UI can send prompts back to the agent | Open-ended |
| A2A | agent ↔ agent | Google | remote agents in isolated trust domains | (transport) |
| AG-UI | agent ↔ user-facing surface | CopilotKit · https://docs.ag-ui.com/ | streaming event protocol for long-running agents (reconnect, mid-run steering, structured + unstructured at once); supports the whole spectrum; A2UI handshake | all |
| A2UI | UI as declarative messages | Google (v0.9 at verification; 1.0 targeted Q3 2026) · https://a2ui.org/ | LLM *structured output* (not tool use) in JSONL: surfaces (composition of components) + data (hydrates variables) + text fallback, against a client-advertised catalog; repairs malformed generations; renderers Lit, Angular, React, Flutter (core), Vue, Swift, json-renderer (ecosystem); transport-agnostic | Declarative |
| json-render | declarative renderer | Vercel | JSON or YAML descriptor → your components | Declarative |
| OpenUI | declarative standard | Thesis | catalog-based UI description | Declarative |
| useComponent / client tools | tool → component | AG-UI SDKs, CopilotKit | register a component with name, description, params, render; the agent invokes it | Controlled |

Protocol triangle: MCP (agent↔tools) · A2A (agent↔agent) · AG-UI (agent↔user). A2UI is the
*payload* for the Declarative tier; MCP Apps the *container* for Open-ended. They interoperate:
an A2UI or AG-UI payload can render inside an MCP App, and an MCP App can be a component inside them.

Hosts supporting MCP Apps at verification: ChatGPT (500+ apps), Claude, Gemini, VS Code, Goose.
