---
name: aisamd-logging-guide
description: >-
  Reference for designing or auditing the logging system of an AI SaMD application on
  Linux that integrates with hospital systems (PACS / DICOM): log planes, PHI rules,
  journald facts, DICOM audit trail, and log-retention floors and ceilings (TH / US / EU).
  Use when designing, reviewing, or gap-analysing logging, audit trails, or log retention
  for a medical-device AI app. For the MedLog wire format itself, use `medlog-ref`.
metadata:
  version: "2026-11-15"
---

# AI SaMD logging guide

How to design, and how to audit, the logging of an AI Software-as-a-Medical-Device
application that receives studies from a hospital PACS, runs inference on Linux, and
returns results to clinicians. Scope: **Linux with systemd**. Windows hosts and Kubernetes
are out of scope.

This skill caches what a model cannot derive: dated regulatory facts, non-obvious
`journald` behaviour, where DICOM tooling leaks patient data, and a set of design rulings.
It is engineering reference, **not legal advice**.

## Establish these first

Every later choice depends on them. Ask; do not assume.

| Input | Options | It decides |
|---|---|---|
| Topology | One hospital server · a fleet of client PCs · both | Sizing, forwarding, who can reach the logs |
| PACS interface | DIMSE (C-STORE auto-routing) · DICOMweb · both | Pointer scheme; which toolkit can leak PHI |
| Trigger | Auto-routed · on-demand by a clinician · both | Who the caller is in each record |
| What the clinician sees | Structured report · overlay / secondary capture · worklist flag | What "output" means |
| Central log store | Hospital SIEM or log store exists · none | Whether the retention tier beyond 90 days exists at all |
| Audit repository | Hospital runs an ATNA audit record repository · none | Whether DICOM audit messages are required |
| Markets | Thailand · US · EU | Which floors apply |
| Parties | Who is the manufacturer; who is the hospital (operator) | Who holds which log, and who owns retention |

## Two views of the same logs

**Planes** say where a log flows. **Categories** say how long it lives.

| Plane (where) | Store | PHI | Category (how long) |
|---|---|---|---|
| **A. Ops** — "is the service healthy?" | stdout → `journald` → optional central store | **None** | 1 Diagnostic |
| **B. Clinical-AI** — "what did the AI see and say, and was it right?" | Local outbox → collector → database | Yes, pseudonymised | 3 AI inference |
| **C. Security audit** — "who accessed or changed what?" | `auditd`, database audit, DICOM audit repository | Minimal, by design | 2 Security / audit |
| Any plane, once an excerpt enters a complaint, CAPA, or vigilance file | Manufacturer QMS | Pseudonymise | 4 QMS evidence — a *state change* |
| Any plane | — | — | 5 Personal data — a *property*; it sets the ceiling |

## Invariants

These hold in every design. A finding against one is a defect, not a preference.

1. **No PHI in the ops plane.** Patient name, patient ID, accession number, birth date,
   report text, pixels, **and DICOM Study / Series / SOP Instance UIDs** all count.
2. **Planes join only on an event UUID and a run UUID.** Never on a patient or study key.
3. **One clinical-AI record per model invocation**, including automatic runs, and the
   record is opened **before** the model runs. A failed inference still leaves a record.
4. **Logging never blocks or fails inference.** Write locally first, deliver later.
5. **PHI-free inference metadata may go to `journald`; the inference record goes to the
   clinical-AI store.** They are two things; do not merge them.
6. **`journald` has no minimum-retention setting.** Every setting is a cap. A 90-day floor
   is engineered by sizing, then verified by a monitor.
7. **Clinical-AI records are never rotated.** No `logrotate`, no journal vacuum. An
   explicit, documented retention job deletes them.
8. **Third-party logging is in scope.** DICOM toolkits, HTTP access logs, and tracebacks
   leak identifiers at debug level and sometimes by default.
9. **A log excerpt attached to a quality record changes clock.** It follows the QMS
   record-retention rule, not the log rule.
10. **Personal data creates no floor.** It only shortens the ceiling.
11. **The manufacturer owns capability and disclosure; the hospital owns retention.**
12. **Regulatory numbers carry a date and an evidence grade.** Re-verify before one goes
    into a quality record, labeling, or a submission.

## Requirement IDs

Rules are numbered so a PR, a design document, or a quality record can cite them. IDs are
stable: never renumber or reuse one; retire it instead.

| Prefix | Area | Defined in |
|---|---|---|
| `PHI-` | Personal data in logs | [planes.md](references/planes.md) |
| `OPS-` | Ops plane on Linux | [linux-platform.md](references/linux-platform.md) |
| `CAI-` | Clinical-AI plane | [clinical-ai-plane.md](references/clinical-ai-plane.md) |
| `SEC-` | Security-audit plane | [security-audit.md](references/security-audit.md) |
| `RET-` | Retention | [retention.md](references/retention.md) |

## Where to look

| Task | Read |
|---|---|
| Decide what goes in which plane; who holds which log | [planes.md](references/planes.md) |
| Configure `journald`, forwarding, sizing, the floor monitor | [linux-platform.md](references/linux-platform.md) |
| Map a PACS workflow onto per-inference records; outcome linkage | [clinical-ai-plane.md](references/clinical-ai-plane.md) |
| Host audit, audited reads, DICOM / IHE ATNA audit messages | [security-audit.md](references/security-audit.md) |
| Find where the DICOM and inference stack leaks PHI; build a leak scan | [phi-leaks.md](references/phi-leaks.md) |
| Choose a retention period; argue for it | [retention.md](references/retention.md) |
| Quote a law, a standard, or a deadline | [regulatory-register.md](references/regulatory-register.md) |
| Run a design session or a gap analysis; labeling duties; pitfalls | [review.md](references/review.md) |

Two ways in, both described in [review.md](references/review.md):

- **Design** — settle the inputs above and the open questions, then choose planes,
  stores, and retention, and write the result into the project's design documents.
- **Analyse** — map where studies enter, where the model is invoked, and where results
  leave; then produce a gap table against the requirement IDs.

## Related skills

- `medlog-ref` — the MedLog protocol: fields, enums, the five write-once endpoints, the
  wire shape. This guide uses MedLog as the clinical-AI plane and never restates it.
- `dicom-standard` — offline, citable DICOM text. Use it for PS3.15 audit messages.
- `dcmtk`, `orthanc-api` — the DICOM tools whose log output [phi-leaks.md](references/phi-leaks.md) covers.
- `deidentify` — scan log samples or support excerpts for PHI before they leave the site.
- `security-architecture` — the wider threat model the audit plane serves.

## Provenance and freshness

Built from two research documents dated 2026-11-10 and 2026-11-15, plus two verification
passes on DICOM audit messages and on toolkit log output. Regulatory facts are graded in
[regulatory-register.md](references/regulatory-register.md), which also holds a
**watch-list** of facts expected to move. No upstream can be diffed by machine, so
freshness is manual: when logging work starts and the register's status date is more than
six months old, re-check the watch-list first.
