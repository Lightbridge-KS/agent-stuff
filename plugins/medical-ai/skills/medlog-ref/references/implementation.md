# Implementing MedLog — integration, interop, storage, privacy

Everything here is from the paper's "Implementing MedLog at scale" section and
Supplementary Note 1. It is guidance, not schema — the normative parts are in
[record-schema.md](record-schema.md) and [wire-protocol.md](wire-protocol.md).

## Where to put the instrumentation

MedLog can be adopted **unilaterally within one health system**, with no vendor
cooperation and without modifying the models. The design move is to intercept at a
chokepoint that already sees every call:

```
        ┌──────────────────────────────────────────────┐
        │  callers: clinicians · patients · agents ·   │
        │           scheduled jobs                     │
        └───────────────────┬──────────────────────────┘
                            ▼
        ╔═══════════════════════════════════════╗
        ║  API gateway  /  LLM proxy  /  sidecar ║ ──emits──► MedLog collector
        ║   ← instrument HERE                    ║            (write-only endpoints)
        ╚═══════════════════╤═══════════════════╝
                            ▼
                    models, tools, agent frameworks
                    (unmodified)
```

- **API gateway / LLM proxy** — intercepts model calls, extracts or augments metadata,
  emits compliant events. The lowest-friction path for legacy and MedLog-naive systems.
- **Sidecar around an agent framework** — wraps tool calls to capture inputs, retrieved
  context, outputs, and uncertainty estimates.
- Both support **incremental adoption**: start with `inference-start` + `human-output`,
  add artifacts and outcomes later.

The hard part is never the emitter. It is **outcome linkage**, which by definition lives
outside the AI workflow and arrives late — budget for a separate job that posts
`/event/outcome` against `event_id`s recorded hours or days earlier.

## Interoperability — reuse, don't invent

MedLog is a schema, not a stack. Existing standards carry it:

| Standard | Role | Mapping |
|----------|------|---------|
| **W3C PROV** | provenance model | record and its fragments → `prov:Entity` · the model invocation → `prov:Activity` · model and user → `prov:Agent` (`prov:SoftwareAgent`, `prov:Person`) |
| **OpenTelemetry** | transport + storage | collectors and backends for the event stream across languages |
| **OpenLineage** | lineage metadata | useful for the User-identity provenance chain |
| **FHIR** | clinical semantics | anchor records to `AuditEvent`, `Patient`, `Condition`, `Observation`, `Practitioner`, `PractitionerRole` |

MedLog also **builds on EHR audit logs**, which already prove event-level logging works
at hospital scale — and which are a source for the Outcomes field (what the clinician did
after seeing the output).

## Storage and retention

Volume from the four published pilots, which differ by three orders of magnitude:

| Pilot | Duration | Patients | Records |
|-------|---------:|---------:|--------:|
| Ho Chi Minh City — tetanus wearables | 289 d | 15 | 3,406 |
| San Diego — SEP-1 abstraction | 89 d | 60 | 3,766 |
| Bern — ICU deterioration | 114 d | 212 | 223,840 |
| New York — attendance prediction | 244 d | 791,319 | 2,914,264 |

Volume tracks **inference frequency and workflow design**, not patient count: the ICU
model scores continuously, the abstraction model fires a handful of times per case.
Estimate from calls/patient/day, never from cohort size.

Retention strategies, in the paper's own terms:

- **Full tracing** during pilots and after major model updates.
- **Sampling or risk-triggered tracing** in steady state.
- **Tiered retention** — long-lived summaries, shorter-lived detailed artifacts.

The Internal-artifacts field is where cost concentrates, and it is the one field optional
even under full conformance. Set its capture policy explicitly.

## Privacy and security

MedLog records contain PHI. Treat the collector as an EHR-class data store.

- Same regime as EHR databases: **HIPAA, HITECH, GDPR, ISO/IEC 27001**; role-based
  access control; audit logging of access to the logs themselves; pseudonymous
  identifiers.
- **Store references, not raw content.** Keep the AI output that informed care in the
  EHR and put a content-addressed pointer in the MedLog record. This is what keeps
  MedLog **outside the HIPAA-designated record set / legal medical record** — a
  deliberate design goal, not an accident.
- Deploy **locally, inside the institutional firewall**. Cross-site work happens on
  de-identified or aggregated records, via secure multi-party computation, homomorphic
  encryption, or federated learning.
- **Adversarial risk to model vendors is real**: large volumes of input-output pairs,
  uncertainty estimates, and reasoning traces enable membership-inference attacks
  (exposing training data) and model-extraction attacks (distilling a proprietary model,
  or reconstructing prompting techniques and tool calls). Governance should require
  technical safeguards and IP protection agreements, or vendors will refuse to
  participate. Ownership tags can be carried in Model instance, Inputs, and Outputs.

The regulatory analogy the paper draws: pooled de-identified records serving
post-market surveillance of medical AI, the way FAERS and the WHO drug-monitoring
programme pool case reports for drugs.

## Low-resource deployment

MedLog explicitly allows **partial or incremental compliance** — it does not require a
full EHR or continuous connectivity.

- **Minimal conformance profile:** Header + Model instance + Outputs. Add fields as
  capacity grows.
- **Write-behind caching:** store records on device (e.g. a smartphone app) and sync to
  the central collector when connectivity returns.
- **No unique patient identifier?** Anchor to encounter-level metadata — visit, time,
  location, department — with optional FHIR linkage when available.
- Maps onto **OpenMRS** and **DHIS2**.
- Lifecycle-aware retention and risk-triggered sampling matter more here, not less.

## Governance — the part that is not technical

Implementation needs clear operational ownership, defined review workflows, and rules for
who may see detailed records. Clinician involvement is load-bearing: which events get
reviewed, how logged outputs are interpreted, and how recurring failure modes are acted
on are clinical judgements, not engineering ones. Governance bodies need strong clinician
representation, and deployments should be framed as a tool for clinical learning rather
than surveillance of professional performance.

The business case works without any data sharing: safety and quality improvement,
liability management, and operational efficiency accrue locally. That matters because the
cautionary precedent is HITECH — ubiquitous EHR adoption, but by 2015, 96% of hospitals
either claimed exclusion from or did not report to specialized public health registries.
Adoption of the record format does not imply adoption of the exchange.

## What MedLog buys you (worth stating when justifying the work)

Demonstrated in the published pilots, not hypothetical:

- **Quantifying a bedside complaint.** Bern clinicians reported frequent alarms right
  after ICU admission; the records showed 16.5% of alarms fell in the first hour, and
  that the rate was the same for patients who later deteriorated (16.4%) and those who
  did not (17.4%). A suppression policy for first-hour alerts was deployed as a result.
- **Finding a failure mode invisible at the bedside.** The same records showed predicted
  risk *falling* as time since the last lab measurement grew — in patients who did go on
  to deteriorate.
- **Measuring model coherence.** The SEP-1 pilot re-ran the same abstraction seven times
  and compared logged outputs (agreement 0.43).
- **Detecting dataset shift.** The Clalit case study caught an LDH distribution shift
  caused by a lab switching test kits; by 18 months ~10% of patients would have had risk
  scores shifted by >0.1%.
- **Linking outputs to downstream actions.** ICU alerts preceded increased laboratory
  testing — a measurable association between model output and clinician behaviour.
