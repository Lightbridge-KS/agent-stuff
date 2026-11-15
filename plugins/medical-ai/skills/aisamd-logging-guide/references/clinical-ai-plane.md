# Clinical-AI plane — per-inference records for a PACS workflow

This plane uses the **MedLog protocol**. The protocol itself — fields, enums, the five
write-once endpoints, the wire shape, version traps — is in the `medlog-ref` skill. Load
it before writing or checking a payload. This file holds only what `medlog-ref` does not:
the mapping to a radiology workflow, and the system rules around the protocol.

Source tags: **[paper]** = MedLog paper guidance; **[rec]** = a design recommendation of
this guide, open to discussion with the product owner.

## Requirements

| ID | Rule | Source |
|---|---|---|
| CAI-01 | One record per model invocation: automatic PACS-triggered runs included, and one per model in a multi-model pipeline | [paper] |
| CAI-02 | The start event is written **before** the model runs, so a failed inference leaves a record | [paper] |
| CAI-03 | Instrumentation sits at one chokepoint (gateway, DICOM router, or sidecar). The model is not modified | [paper] |
| CAI-04 | An emitter failure never stops or delays inference: enqueue locally and durably, deliver in the background | [paper] |
| CAI-05 | `model_version` = released software version + weights hash, for example `2.3.1+weights.sha256-9f2c41e0`. It matches the QMS release record. `model_card_url` points to the controlled document | [rec] |
| CAI-06 | The **operating point** (decision threshold, triage-rule version) is logged with each inference. The same weights at another threshold behave like another device | [rec] |
| CAI-07 | One `run_id` per study per pipeline execution. Each model posts its own start event with that `run_id`; a downstream model sets `parent_event_id` to the upstream start event | [rec] |
| CAI-08 | The target identifier is a keyed pseudonym of the patient number (PHI-03), never the raw number | [rec] |
| CAI-09 | Pointers, not pixels: inputs and outputs are absolute URIs — a DICOMweb URL or `urn:oid:<UID>` | [paper] |
| CAI-10 | Non-identifying acquisition metadata goes in **one** namespaced extension object, `inputs.x_<vendor>`: modality, body part, view, manufacturer, scanner model, protocol, slice thickness, kVp, pixel spacing. Confirm the collector accepts extra keys | [rec] |
| CAI-11 | The output event records **what the clinician saw** — report text, overlay, triage flag — not the raw score alone | [paper] |
| CAI-12 | The output event is posted when the result is delivered to the viewer or worklist, and says so. If the viewer can report "opened", post it then | [rec] |
| CAI-13 | Failure signalling is decided explicitly. The protocol has no failure event: a start event with no output event means "no result delivered". Optionally add an artifact event of type `other` that points at the incident | [rec] |
| CAI-14 | Idempotency: the event UUID is frozen at enqueue and reused on every retry; the collector treats a duplicate UUID as already accepted | [rec] |
| CAI-15 | The store is append-only at the database layer: the writer role has `INSERT` only | [rec] |
| CAI-16 | The store is treated like the health record: TLS in transit, encryption at rest, inside the hospital firewall, role-based access, a view per audience, and every read audited (SEC-02) | [paper] |
| CAI-17 | The collector runs as a separate service and database from the app — ideally a separate host or VM | [rec] |
| CAI-18 | Outcome linkage is a separate, delayed job. It covers AI-**negative** studies too, and records linkage strength and who or what judged | [paper] |
| CAI-19 | Internal artifacts (heatmaps, uncertainty) follow a written capture policy | [paper] |
| CAI-20 | Test and validation runs never reach the production collector | [rec] |
| CAI-21 | The logger is monitored: outbox backlog, parked events, and the share of start events with no output event | [rec] |
| CAI-22 | The output event carries `latency_ms`, measured from study receipt to result delivered | [rec] |
| CAI-23 | Each inference also writes one PHI-free metadata line to the ops plane with `LOG_CATEGORY=ai` and the event UUID | [rec] |
| CAI-24 | Governance is named: an owner, a review workflow, clinician representation. The purpose is clinical learning, not staff surveillance | [paper] |

## Field mapping

Keys are the MedLog wire keys; check names and enum values in `medlog-ref`.

| Field | Wire key | Value in a PACS workflow | Example |
|---|---|---|---|
| Model | `model_instance.model_id` | Product or model name | `cxr-triage` |
| | `model_instance.model_version` | CAI-05 | `2.3.1+weights.sha256-9f2c41e0` |
| Caller | `user_identity.caller_type` | `service` when auto-routed; `clinician` on demand | `service` |
| | `user_identity.caller_id` | Router or AE title; or the clinician's staff ID | `dicom-router/AE:AI_SCP` |
| Target | `target_identity.target_id` | CAI-08 | `pid-7c1e9a52` |
| Inputs | `inputs.input_uri` | Study pointer, CAI-09 | `https://pacs.example.org/dicom-web/studies/<StudyUID>` |
| | `inputs.x_<vendor>` | CAI-06, CAI-10 | `{"modality":"CR","operating_point":"triage-v4@0.62"}` |
| Artifact | `artifact.artifact_type` | `explanation` for a heatmap; `other` for uncertainty or an error marker | `explanation` |
| Output | `output.output_type` | `text` for a structured report; `image` for an overlay or secondary capture | `text` |
| | `output.output_uri` | The result's SOP Instance | `urn:oid:<SOPInstanceUID>` |
| | `output.summary` | **Exactly what was displayed**, plus the triage flag | `Suspected pneumothorax, right. p=0.91. URGENT` |
| Outcome | `outcome.outcome_type` | From the comparison with the final report | `validated` |

Record upstream initiators as a provenance chain where known: modality → PACS routing
rule → router.

The Study UID inside `input_uri` is PHI. It is acceptable here because this plane is the
PHI plane; it is never acceptable in the ops plane.

## Lifecycle of one study

```
Modality   PACS        AI gateway / router       AI model     Collector          RIS (later)
  │C-STORE  │                │                      │             │                  │
  │────────►│  auto-route    │                      │             │                  │
  │         │───────────────►│ ① start ──────────────────────────►│ (outbox → POST)  │
  │         │                │── run ──────────────►│             │                  │
  │         │                │◄── result ───────────│             │                  │
  │         │                │ ② artifact ───────────────────────►│ (capture policy) │
  │         │◄─ SR / overlay │ ③ output ─────────────────────────►│                  │
  │         │  clinician reads and signs the final report ──────────────────────────►│
  │         │                │      ④ outcome job (hours–days) ──►│◄── final report ─│
  │         │  viewer 👍/👎 ─────────► ⑤ feedback ────────────────►│                  │
```

Failure path: ① is posted, the model errors, no ③ follows. The ops line with the same
event UUID holds the technical detail.

## Outbox invariants (CAI-04, CAI-14)

A model will write the emitter; these are the properties to check.

- Durable local queue (for example SQLite in WAL mode) written **before** any network call.
- The event UUID is the primary key and is fixed at enqueue.
- `201`, including a duplicate → delete from the queue.
- `400` → **park** for a human; never retry forever. Alert on any parked event.
- Network error, `401` / `403`, `5xx` → retry with exponential backoff, capped (5 minutes).
- The flush loop catches its own exceptions; it must not die silently.
- The enqueue call never raises on a network problem.
- The queue holds PHI until flushed → PHI-07.

## Store invariants (CAI-15 to CAI-17)

- One row per event; the event UUID is the primary key; duplicates are ignored on insert.
- **No foreign key** on `parent_event_id`: after retries, events arrive out of order.
- Validate every body against the protocol schema; reject what does not conform.
- The servers named in the public specification are not production collectors. The
  hospital runs its own, inside the firewall.
- Views per audience: case-level with controlled re-identification for clinical review;
  pseudonymised for the ML team; de-identified or aggregated for regulators and
  multi-site work.
- Large volumes of input–output pairs and uncertainty data enable model-extraction and
  membership-inference attacks. Restrict access to detailed artifacts.

## Outcome linkage (CAI-18)

A scheduled job that: finds start events from the last *N* days with no outcome; fetches
the final report by accession; compares it with the AI output; posts an outcome event
that points at the original start event.

| `outcome_type` | Radiology meaning (proposed) |
|---|---|
| `validated` | The final report agrees: confirmed positive or confirmed negative |
| `contradicted` | The final report disagrees: false positive or false negative |
| `partial` | Some findings match; or the right finding with the wrong side or size class |
| `unknown` | No final report yet, an ambiguous report, or no ground truth |

- Record the linkage source and strength (same accession vs temporal; final report vs
  addendum vs pathology vs follow-up) and the judge (a clinician, or parser version *x*).
- A language model that judges agreement is itself an AI invocation and gets its own record.
- A later, stronger outcome is a **new** event. Nothing is edited.
- Feedback (thumbs, rating) is voluntary and biased: a signal, not ground truth.

## Capture policy and volume (CAI-19)

```
events/day ≈ studies/day × model invocations/study × events/invocation
bytes/day  ≈ events/day × 1–2 KB   (+ artifact files, if stored)
```

Illustrative: 300 studies/day × 1 model × 4 events ≈ 1,200 events/day ≈ 0.7 GB/year. Every
heatmap kept at ~100 KB adds ≈ 11 GB/year. **Artifacts are where cost concentrates.**

| Phase | Internal artifacts | Events |
|---|---|---|
| Pilot, and the first weeks after a model update | 100 % | 100 % |
| Steady state | Random sample (5–10 %) plus risk-triggered: every `contradicted`, every urgent triage, every high-uncertainty case | 100 % |
| Archive | Delete detailed artifacts after the period in [retention.md](retention.md) | Per RET-03 |

## What the records answer

- **Reliability** — start events with no output; outbox backlog; latency percentiles.
- **Real-world performance** — validated / contradicted / partial rates, overall and by
  scanner manufacturer, protocol, site, and time of day.
- **Dataset shift** — distributions of acquisition metadata and of output scores over time.
- **Workflow effect** — time-to-result for urgent triage; alert rate by hour.
- **Change impact** — before and after each `model_version`.

A complaint, incident, or change request should cite the event UUIDs, run UUIDs, and
`model_version` it concerns. That link is what turns a log into post-market evidence.
