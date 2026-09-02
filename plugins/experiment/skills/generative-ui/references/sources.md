# Sources

## Official docs

Fetch these before quoting a version, API or default; `protocols.md` carries only the shape.

- AG-UI — https://docs.ag-ui.com/
- A2UI — https://a2ui.org/
- MCP Apps — https://modelcontextprotocol.io/extensions/apps/overview.md

## Talks

Three talks, June–July 2026. One line per lesson kept; everything else was pruned.

1. **Gus Iwanaga (commercetools), "The End of the Static Screen", AI Engineer World's Fair 2026-07-02** — https://www.youtube.com/watch?v=QrMcNe2jjt8
   - The failure demo: one intent, four layouts, drifting copy → the composition contract (§5) and the copy rule (§7).
   - "The catalog is the contract between the agent and your UI; every property matters" → §4.
   - Atomic design, templates → slots → sub-slots → eligible categories, resolved bottom-up → §5.
   - "We don't design the pixel anymore" → the people pitfall (§9).
2. **Ruben Casas (Postman), "Beyond Components", AI Engineer Europe 2026-06** — https://www.youtube.com/watch?v=hCMrEfPG2Yg
   - Two orthogonal questions: where the UI runs vs what the model emits → §1.
   - Declarative as "the perfect balance today" → the §2 default.
   - "If you don't trust third-party code, don't trust LLM-generated code" → §6.
   - Shared artifacts (Excalidraw canvas) over Jarvis: where the field is heading.
3. **A2UI · AG-UI · MCP Apps owners + AKQA, "Generative UI for any agent, anywhere", Google Cloud Next 2026-06** — https://www.youtube.com/watch?v=UsMDkEsR-ok
   - "No single generative UI solution is good for all use cases" → pick per surface (§2).
   - Controlled / Declarative / Open-ended pros, cons and "great for" rows → §2 table.
   - Structured output, not tool use; surfaces + data + fallback; catalog = what the client advertises → §4, §7.
   - Security: image exfiltration, hidden forms, supply chain; "every approach has a risk profile" → §6.
   - AKQA: intent → interpretation layer → brand brain (knowledge + governance) → generative interface; structured intent (functional, emotional, social).
