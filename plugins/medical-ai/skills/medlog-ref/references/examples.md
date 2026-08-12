# MedLog records — worked examples

Four interaction archetypes from the paper (Figure 1b / Supplementary Figure 1), one real
pilot record, and the shape the pilot code actually emits. All identifiers below are the
paper's own synthetic examples.

These are **shape A** (paper prose) unless marked otherwise — good for explaining MedLog
and for seeing what belongs in each field. To send one, translate to the wire shape in
[wire-protocol.md](wire-protocol.md).

## The four archetypes

What varies between them is *who calls* and *what the target is* — the other seven fields
behave the same.

| | Caller | Target | Distinguishing feature |
|---|--------|--------|------------------------|
| Patient-AI | patient (MRN) | a document | consent-form summarisation; thumbs feedback |
| Provider-AI | clinician (NPI) | a patient | treatment recommendation; outcome followed up |
| Administrator-AI | staff ID | a claim | RAG over policy DB; 1–5 rating |
| AI-AI | **another model** | a patient + episode | `run_id` + `parent_event_id`; no feedback |

### 1. Patient-AI — consent-form summary

| Field | Value |
|-------|-------|
| Header | MedLog version 0.0.1 · Event ID 43782 · 2025-01-20T09:15:00Z · Invoked via PatientPortal v2.3 on server node-doc-001 |
| Model instance | SummDoc-AI v2.1 |
| User identity | Process ID 25030 · Immediate caller MRN-6304881183 |
| Target identity | Document ID IC-2025-001 — informed consent form for trial #CT2025-04 |
| Inputs | Prompt: "Please summarize the main points and key responsibilities outlined in the attached informed consent form, focusing on risks, benefits, confidentiality, and any follow-up obligations for participants." |
| Internal artifacts | Chain-of-thought: "Headings matching common ICF sections include risk, benefit…" |
| Outputs | Summary: "This consent form outlines the purpose of the clinical trial, describes the potential risks…, and details possible benefits… Participation is voluntary with the right to withdraw at any time." |
| Outcomes | Consent form reviewed: Yes — patient indicated the summary was clear, signed 2025-01-20 |
| User feedback | 👍 |

### 2. Provider-AI — off-label treatment recommendation

| Field | Value |
|-------|-------|
| Header | 0.0.1 · Event ID 61947 · 2025-01-10T10:05:00Z · RareCancer-CDS interface v4.5 on node-cds-007 |
| Model instance | OncoAssist-AI v3.4 · RAG database: EHR Warehouse v3.1 |
| User identity | Process ID 78201 · Immediate caller NPI-5948162307 |
| Target identity | Patient ID MRN-8374201965 |
| Inputs | Prompt: "Given the patient's rare subtype of alveolar soft part sarcoma and progression on standard protocols, what off-label or experimental therapy options could offer clinical benefit…?" |
| Internal artifacts | RAG retrieval: 14 case reports from EHR using TKIs for alveolar soft part sarcoma; PubMed references showing sunitinib activity in TFE3 rearrangements |
| Outputs | Recommendation: Off-label sunitinib 37.5 mg PO daily with q2wk platelet monitoring |
| Outcomes | Treatment administered: Yes, sunitinib initiated 2025-01-15 · Follow-up: mild fatigue, manageable nausea; platelets stable ~115,000/μL; six-week imaging suggests stable disease |
| User feedback | Comment: "Would be helpful if recommendations included dosing adjustments." |

Note the shape of a good `Outcomes` entry: **the action taken and the observed result**,
not just "accepted".

### 3. Administrator-AI — claim denial prediction

| Field | Value |
|-------|-------|
| Header | 0.0.1 · Event ID 85230 · 2025-01-28T11:20:00Z · AdminPortal v3.7 on node-claims-002 |
| Model instance | ClaimPredict-AI v1.2 · RAG database: InsuranceReg-DB v4.0 |
| User identity | Process ID 65341 · Immediate caller Staff-3947523 |
| Target identity | Insurance claim ID CL-2025-009 — cardiovascular surgery authorization |
| Inputs | Prompt: "Estimate the likelihood that the insurance company will deny coverage… Plan Type B, last updated 2021. Estimated procedure cost $80,000." |
| Internal artifacts | RAG retrieval: six historical Plan-Type-B claims for high-value cardiovascular procedures; policy note #POL-CV332 (increased scrutiny above $50,000) |
| Outputs | Predicted denial probability: 65.3% |
| Outcomes | Claim status: pending submission; administrator prepared supplemental documentation before final submission 2025-02-01 |
| User feedback | Rating: 4 / 5 |

### 4. AI-AI — orchestrator invokes a sepsis model

The one that exercises linkage. Note `Run ID` **and** `Parent event ID`, a model as
caller, and empty feedback — no human was in this loop.

| Field | Value |
|-------|-------|
| Header | 0.0.1 · Event ID 98214 · **Run ID ICU-Triage-Run-5543** · **Parent event ID 98213** · 2025-01-12T03:42:00Z · ICU-Orchestrator v2.9 on node-icu-014 |
| Model instance | SepsisPredictor-AI v4.1 · Training data: ICU-EHR dataset v2024.07 |
| User identity | Process ID 86145 · Immediate caller **TriageAgent-AI v5.7** · Upstream initiator: autonomous ICU workflow (scheduled hourly triage cycle) |
| Target identity | Patient ID MRN-4928810372 · Episode ID ICU-Admission-2025-00114 |
| Inputs | Structured: vitals (HR 72, MAP 62 mmHg, Temp 38.9 °C, RR 28, SpO₂ 96%), labs (WBC 14.2k/μL, lactate 3.8 mmol/L), demographics (F, 64y) |
| Internal artifacts | Agent trace: TriageAgent-AI → SepsisPredictor-AI · Predictive entropy 0.21 · SHAP highlights lactate and MAP as top contributors |
| Outputs | Risk score: 78.6% probability of sepsis within 6 h · Confidence ±6.5% · Explanation: elevated lactate and hypotension driving majority of risk |
| Outcomes | Action: TriageAgent escalated to attending · Response: broad-spectrum antibiotics within 45 min · Trajectory: lactate 2.1 mmol/L by 12 h, patient stabilized |
| User feedback | None |

The **upstream initiator** line is the provenance chain the spec asks for: the immediate
caller is another model, but the chain terminates in a scheduled job, not a person.

## A real record: SEP-1 sepsis quality abstraction (San Diego pilot)

From Figure 4a — an actual production record, and the closest thing to a canonical
key-naming example. Note it is one **LLM call within a multi-step workflow**: the
abstraction asks many questions per patient, each generating its own record, all sharing
a `run_id`.

```json
{
  "header": {
    "medlog_version": "0.0.1",
    "event_id": "551b1676-1837-4278-988d",
    "timestamp": "2026-01-10T05:31:19",
    "system_info": "SEP-1 Abstraction AI",
    "run_id": "492dac48-dd7d-485e-8891"
  },
  "model_instance": { "model_id": "Llama-3.1-8B-Instruct", "model_version": "2024-07-18" },
  "user_identity":  { "process_id": "3023" },
  "target_identity": { "patient_id": "P18" },
  "inputs": {
    "prompt": "You are a CMS quality abstractor. Your task is to review the given medical note and answer the…",
    "question": "Is there an explicit positive qual…"
  },
  "internal_artifacts": {
    "chain_of_thought": "The note contains an explicit…",
    "extracts": "Sepsis with acute kidney injury"
  },
  "outputs":  { "option": "Y" },
  "outcomes": { "category": "E - In-Numerator Population" },
  "user_feedback": { "qps_analyst": "Agree, case passes." }
}
```

What this pilot did with the records: ran the same abstraction seven times and compared
outputs across runs to measure model coherence (agreement 0.43). That analysis is only
possible because each call was logged separately with a shared `run_id` — a concrete
argument for per-call granularity over per-workflow logging.

## What the pilot code actually emits (shape C)

`mims-harvard/MedLog` → `src/vietnam_analysis.py:184` — the tetanus/wearable pilot. This
is what you will find if you clone the repo looking for a reference implementation:

```python
record = {
    "header": {
        "medlog_version": "0.0.1",
        "event_id": str(uuid.uuid4()),
        "timestamp": row["alert_datetime"].isoformat(),
        "system_info": "Vietnam Clinical Alert System",
        "timezone": "ICT",
    },
    "model_instance": {"model_id": "24EIC-AI-Alert", "model_version": "1.0.0"},
    "user_identity": {},
    "target_identity": {"patient_id": row["patient_id"]},
    "inputs": {
        "current_ablett_grade": ...,
        "context": {"day_of_week": ..., "hour": ...},
    },
    "internal_artifacts": {"model_probability": ...},
    "outputs": {"model_output": ...},
    "outcomes": {
        "assessment_timestamp": ...,
        "response_time_minutes": ...,
        "event_at_alert": ...,
        "clinical_note": ...,
    },
    "user_feedback": {"clinician_assessment": ...},
}
```

Three things to take from it, and one not to:

- It is **one assembled JSON document**, not five events — the pilot wrote records
  retrospectively from an alert export, so there was nothing to assemble incrementally.
- `header.timezone` and `header.system_info` are **not in the spec**. Deployments add
  keys they need.
- `user_identity` is empty — a fully automated alerting system with no recorded caller.
  Real conformance is partial.
- **Do not copy this as the wire format.** It validates against nothing.
