# MedLog record schema — the nine fields across all three shapes

Ground truth: [`assets/openapi-0.0.1.yaml`](../assets/openapi-0.0.1.yaml). Where this
file and the prose disagree, the spec wins.

## Reconciliation table

The same nine concepts, named three ways. **Column B is what you send over the wire.**

| # | Concept | A. Paper prose | B. Wire (openapi 0.0.1) | C. Pilot code |
|---|---------|----------------|--------------------------|----------------|
| 1 | Provenance / context | `Header` | *(flattened onto every event)* `medlog_version`, `event_id`, `timestamp`, `run_id`, `parent_event_id` + `system_metadata{}` | `header{medlog_version, event_id, timestamp, system_info, timezone}` |
| 2 | Model | `Model instance` | `model_instance{}` — InferenceStart only | `model_instance{model_id, model_version}` |
| 3 | Caller | `User identity` | `user_identity{}` — InferenceStart only | `user_identity{}` |
| 4 | Subject | `Target identity` | `target_identity{}` — InferenceStart only | `target_identity{patient_id}` |
| 5 | Input | `Inputs` | `inputs{}` — InferenceStart only | `inputs{…ad-hoc…}` |
| 6 | Internals | `Internal artifacts` | `artifact{}` — its own event | `internal_artifacts{…ad-hoc…}` |
| 7 | Human-facing output | `Patient- and clinician-facing outputs` | `output{}` — its own event | `outputs{…ad-hoc…}` |
| 8 | Outcome | `Outcomes` | `outcome{}` — its own event | `outcomes{…ad-hoc…}` |
| 9 | Feedback | `User feedback` | `feedback{}` — its own event | `user_feedback{…ad-hoc…}` |

Two structural consequences:

- **Fields 2–5 travel together** in the opening `InferenceStart` event. Fields 6–9 each
  get their own event, sent whenever the information exists.
- **The pilots do not validate against the spec.** Inside each block they use whatever
  keys the deployment needed (`current_ablett_grade`, `model_probability`,
  `response_time_minutes`, `clinician_assessment`). Treat pilot records as evidence of
  how loose real conformance is, not as a schema.

## Envelope: `BaseEvent`

Every one of the five events carries this. Four fields are **required**:

| Key | Type | Required | Notes |
|-----|------|:--------:|-------|
| `event_id` | string (uuid) | **yes** | Unique to this event |
| `timestamp` | string (date-time) | **yes** | |
| `medlog_version` | string | **yes** | `"0.0.1"` — see the version trap below |
| `system_metadata` | object | **yes** | See below |
| `run_id` | string (uuid) | no | Constant across all events in one inference run |
| `parent_event_id` | string (uuid), nullable | no | The event this one expands on |

`system_metadata` (all optional): `hostname`, `app_name`, `proc_id`, `latency_ms` (int32).

> **Version trap.** The spec annotates `medlog_version` with `example: '1.0'`, but the
> spec's own `info.version` is `0.0.1` and *every* real record — pilot code, the SEP-1
> figure, all four paper archetypes — emits `"0.0.1"`. Send `"0.0.1"`. Treat the `'1.0'`
> example as an upstream defect, not a second supported version.

## Payload objects

Every enum below is closed. These are the values that get invented; copy them verbatim.

### `ModelInstance` — no required fields

| Key | Type |
|-----|------|
| `model_id` | string (e.g. `gpt-4o`) |
| `model_version` | string (e.g. `2025-05-01`) |
| `model_card_url` | string (uri) |
| `data_sheet_url` | string (uri) |

Paper adds, when no datasheet exists: record the training-data version, any databases
queried for RAG, and any test-time edits to the model.

### `UserIdentity` — no required fields

| Key | Type |
|-----|------|
| `caller_type` | **`clinician` \| `patient` \| `admin` \| `service`** |
| `caller_id` | string |

Paper: log at minimum the **immediate calling process**; record upstream initiators as a
provenance chain when possible. Humans by EHR identifier (NPI, MRN). Callers may be AI
agents or scheduled jobs.

### `TargetIdentity` — no required fields

| Key | Type |
|-----|------|
| `target_type` | **`patient` \| `document` \| `claim` \| `none`** |
| `target_id` | string |

Optional as a whole — models with no discrete subject use `none`.

### `Inputs` — no required fields

| Key | Type |
|-----|------|
| `prompt` | string |
| `input_uri` | string (uri) — pointer to bulky input data |

The spec is deliberately thin here. Structured predictive models put feature vectors in
`prompt`-adjacent custom keys in practice (see pilot code); imaging and genomics use
`input_uri`.

### `Artifact` — requires `artifact_type`, `artifact_uri`

| Key | Type |
|-----|------|
| `artifact_type` | **`text_chunk` \| `reasoning_trace` \| `tool_call` \| `explanation` \| `other`** |
| `artifact_uri` | string (uri) |
| `mime_type` | string |
| `description` | string |

Covers chain-/tree-/graph-of-thought traces, RAG context, agent interaction traces,
uncertainty estimates (confidence, prediction intervals, entropy), and interpretability
output (attribution maps, feature importance, saliency). For self-evolving models it may
also hold model-state or memory snapshots.

### `HumanOutput` — requires `output_type`, `output_uri`

| Key | Type |
|-----|------|
| `output_type` | **`text` \| `image` \| `video` \| `audio` \| `other`** |
| `output_uri` | string (uri) |
| `summary` | string |

Any triage level or risk score that decides whether a record is flagged for human review
belongs here.

### `Outcome` — requires `outcome_type`

| Key | Type |
|-----|------|
| `outcome_type` | **`validated` \| `contradicted` \| `partial` \| `unknown`** |
| `occurred_at` | string (date-time) |
| `description` | string |
| `evidence_uri` | string (uri) |

Linkage is often indirect and delayed. Partial linkage still has value; the *strength* of
a linkage may itself be recorded to support tiered evidence standards. Sources include
provider attestations, temporal proximity, trial emulation, automated queries, and EHR
audit logs showing what the clinician did after seeing the output.

### `Feedback` — requires `feedback_type`

| Key | Type |
|-----|------|
| `feedback_type` | **`rating` \| `thumbs` \| `text` \| `survey`** |
| `rating_value` | number, **0–5** |
| `comment` | string |

### `Error` — requires `message`

`message`, `code`, `details{}`.

## Conformance: minimum viable vs full

MedLog explicitly permits **partial and incremental compliance**. Use this to score
existing logging rather than treating the standard as all-or-nothing.

| Field | Minimum profile | Full profile | Typical gap in existing systems |
|-------|:---------------:|:------------:|---------------------------------|
| Header | **required** | required | Usually present as a timestamp, but missing `medlog_version` and a stable `event_id` |
| Model instance | **required** | required | Model name logged; **version** usually not — this is the single most common gap |
| User identity | — | required | Service account logged; the human who initiated it is not |
| Target identity | — | required (when applicable) | Often present as patient ID |
| Inputs | — | required | Often only a hash or nothing; bulky inputs unreferenced |
| Internal artifacts | — | **optional even in full** | Nearly always absent; governed by capture policy |
| Outputs | **required** | required | Present, but often only the raw score, not what the human saw |
| Outcomes | — | required *when feasible* | Almost always absent — needs a separate linkage mechanism |
| User feedback | — | required | Absent unless a UI collects it |

The minimum profile — **Header + Model instance + Outputs** — is the paper's stated
low-resource conformance floor. Everything else is added as capacity grows.

Two levels of logging are supported by design: **compact records** for system-wide
monitoring, and **detailed traces** for workflows needing reconstruction or review. The
Internal-artifacts field is where that choice bites; capture policies named in the paper
are continuous logging, random sampling, risk-triggered collection, and enhanced tracing
after major updates or during phased deployment.
