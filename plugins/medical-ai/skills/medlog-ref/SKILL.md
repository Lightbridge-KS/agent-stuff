---
name: medlog-ref
description: >-
  Reference for the MedLog protocol — event-level logging of clinical AI: record fields,
  write-once event endpoints, enums, instrumentation and audit. Use whenever MedLog is
  mentioned, when designing or reviewing logging/audit trails for a deployed clinical AI
  model, or when asked to emit, parse, or assess a MedLog record.
metadata:
  version: "2026-08-15"
---

# MedLog Protocol Reference

MedLog is a protocol for **event-level logging of clinical AI**: every time a model is
invoked — by a human, another algorithm, or a scheduled job — one record is created.
It is explicitly modelled on `syslog`, and fills the gap that model cards and datasheets
leave: those document a model *before* deployment, MedLog records what happens *during* it.

Spec version **0.0.1** (pre-1.0 — expect movement). Paper: arXiv 2510.04033.

## The nine fields

One record per model invocation. Canonical snake_case keys in parentheses.

| # | Field | Key | Holds |
|---|-------|-----|-------|
| 1 | Header | `header` | Provenance + execution context: `medlog_version`, `event_id`, `timestamp`, system info. Optionally `run_id` / `parent_event_id` for multi-stage linkage. |
| 2 | Model instance | `model_instance` | Model + version identifiers, model-card and datasheet URLs, RAG/training-data version. |
| 3 | User identity | `user_identity` | The process, service, or workflow that invoked the model. Human users by NPI/MRN; may be another AI. |
| 4 | Target identity | `target_identity` | The entity the output is *about* — patient ID, document ID, claim ID. Optional. |
| 5 | Inputs | `inputs` | Prompts, feature vectors, structured fields — or a stable pointer when the data is bulky (imaging, genomics). |
| 6 | Internal artifacts | `internal_artifacts` | Reasoning traces, RAG context, uncertainty estimates, attribution maps. **Optional**, capture-policy driven. |
| 7 | Patient-/clinician-facing outputs | `outputs` | What the human actually saw: risk scores, generated text, recommendations, explanations. |
| 8 | Outcomes | `outcomes` | Clinical action taken and observed result. Linked *later*, often indirectly. |
| 9 | User feedback | `user_feedback` | Ratings, thumbs, free-text comments. |

`must`-level requirement from the paper: **the header must carry the MedLog protocol
version** the record complies with. That is the interoperability anchor.

## The #1 source of bugs: three shapes, all called "MedLog"

```
┌────────────────────────────────────────────────────────────────────────────┐
│  A. THE PAPER (prose)          B. THE WIRE (openapi 0.0.1)   C. PILOT CODE │
│  ────────────────────          ───────────────────────────   ───────────── │
│  ONE record, 9 fields          FIVE write-once events        ONE nested    │
│  Field 1 is "Header"           No "header" field at all —    JSON blob     │
│                                  flattened onto BaseEvent    Field 1 is    │
│  Human-readable tables         + `system_metadata`             `header`    │
│  in Figure 1b / Suppl. Fig 1                                              │
│                                POST /event/inference-start   snake_case,   │
│  What you cite in a paper      POST /event/internal-artifact ad-hoc keys   │
│                                POST /event/human-output      inside each   │
│                                POST /event/outcome           block         │
│                                POST /event/user-feedback                   │
│                                                                            │
│  → Use A to explain MedLog · B to IMPLEMENT it · C to read the pilot repo │
└────────────────────────────────────────────────────────────────────────────┘
```

Do not blend them. Concretely, the traps:

- **`header` is not a wire field.** On the wire, `medlog_version` / `event_id` /
  `timestamp` sit at the *top level* of every event, with host details under
  `system_metadata`. The nested `header` object appears only in the paper and pilot code.
- **Upstream contradicts itself on field 1.** The paper's nine open with *header*; the
  OpenAPI `info.description` lists the same nine with **`metadata`** instead.
- **`medlog_version` is `"0.0.1"`.** The spec's `example: '1.0'` is an upstream defect —
  every real record (pilot code, SEP-1 figure, all paper examples) says `0.0.1`.
- **No syslog fields.** `severity`, `facility`, `PRI`, `MSGID` are syslog's, not
  MedLog's. The analogy is architectural, not a field mapping.
- **Enums are closed and short.** Six of them, all in `references/record-schema.md`.
  Guessing `caller_type: "doctor"` (it is `clinician`) is the classic failure.

## Records are assembled incrementally, not written at once

```
t0  InferenceStart   → creates event_id (+ run_id if multi-stage)
                       { model_instance, user_identity, target_identity, inputs }
t1  InternalArtifact → CoT / RAG context / uncertainty      ─┐
t2  HumanOutput      → what the human actually saw           ├─ each references the
t3  Outcome          → clinical action, linked hours later   │  event_id; append-only
t4  UserFeedback     → rating / thumbs / free text          ─┘  write-once
                                    ↑
                    a record exists even when inference FAILS —
                    that is the point of writing t0 before the model returns
```

Multi-stage and agentic workflows link with `run_id` (constant across the run) and
`parent_event_id` (the event this one expands on). No orchestration architecture is
imposed.

## syslog vs MedLog

| | `syslog` | MedLog |
|---|---|---|
| Purpose | event messages → central log server | event-level logging of clinical AI |
| Users | IT and security teams | clinicians, AI/ML engineers, safety regulators |
| Granularity | one record per event | one record per **model invocation** |
| Privacy | clear text, no default encryption | contains PHI; **encryption required** |
| Storage | ≳ KB–GB/day per hospital | ≳ GB–TB/day per hospital |

## Where to look

| Task | Read |
|------|------|
| Emit a record / call the collector | [wire-protocol.md](references/wire-protocol.md) |
| Get a field name, type, or enum right | [record-schema.md](references/record-schema.md) |
| Audit existing logging for conformance | [record-schema.md](references/record-schema.md) — minimum-viable vs full column |
| See a real, complete record | [examples.md](references/examples.md) |
| Instrument without touching the model | [implementation.md](references/implementation.md) — gateway / proxy / sidecar |
| Map to FHIR, W3C PROV, OpenTelemetry | [implementation.md](references/implementation.md) |
| Plan storage, retention, or privacy controls | [implementation.md](references/implementation.md) |
| Deploy without full EHR infrastructure | [implementation.md](references/implementation.md) — low-resource profile |
| Confirm the spec has not moved | `uv run scripts/check_freshness.py` |

The machine-readable spec ships with this skill at
[`assets/openapi-0.0.1.yaml`](assets/openapi-0.0.1.yaml) — treat it as ground truth when
this reference and the prose disagree.

## Provenance and freshness

This skill caches the stable, high-collision core (fields, endpoints, enums) and points
upstream for prose depth. Cached from:

| Source | Pin |
|---|---|
| Paper | arXiv 2510.04033, *A global log for medical AI* |
| Spec snapshot | `mims-harvard/MedLog` @ `adb6961` — verified identical to the live spec on 2026-08-12 |
| Live spec | <https://medlogprotocol.ai/api-reference/openapi.yaml> |
| Doc index for agents | <https://medlogprotocol.ai/llms.txt> — per-field pages at `/specification/<field>.md` |

**The spec is not on the repo's `main` branch.** `openapi.yaml` was added, fixed, then
dropped in the "MedLog pilots" commit; the live site is now the canonical home. Do not
conclude from its absence in a fresh clone that no spec exists.

MedLog is at 0.0.1 and pre-1.0 schemas move. Run `uv run scripts/check_freshness.py`
when MedLog work comes up — it diffs the live spec against the pinned snapshot and exits
non-zero on drift. On drift, re-read `/specification/overview.md` from `llms.txt` before
trusting anything below.
