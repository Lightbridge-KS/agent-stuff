# Planes, custody, and the PHI rules

## The three planes

```
            Modality ──► PACS ── auto-route / query ──┐
                                                      ▼
                                 ┌─────────────────────────────────┐
   clinician (on-demand) ──────► │  AI gateway / DICOM router      │ ◄── instrument HERE
                                 │  (one chokepoint)               │
                                 └───┬──────────────────┬──────────┘
                                     ▼                  │
                                  AI model              │
                 result back  ◄──────┘                  │
                 to the viewer                          │
   ┌────────────────────────────────────────────────────┼─────────────────────────────┐
   │ A. OPS                   │ B. CLINICAL-AI          │ C. SECURITY AUDIT            │
   │ journald → central store │ outbox → collector → DB │ auditd · DB audit ·          │
   │ NO PHI                   │ PHI · encrypted ·       │ DICOM audit repository       │
   │ errors, latency, health  │ append-only             │ who touched what             │
   └──────────────────────────┴─────────────────────────┴──────────────────────────────┘
              ▲     joined only by event UUID / run UUID — never by patient or study     ▲
```

| | A. Ops | B. Clinical-AI | C. Security audit |
|---|---|---|---|
| Audience | Engineers, operations | Clinicians, ML team, QA/RA, safety reviewers | IT security, data-protection officer, auditors |
| Content | Errors, stack traces, latency, queue depth, DICOM association status | Model, caller, target, input pointers, outputs, outcomes, feedback | Logins, privilege use, configuration changes, reads of the clinical-AI store, DICOM access events |
| Mutability | Rotated by size and age | **Write-once** | Append-only, protected |
| Retention tool | `journald` limits, central-store policy | An explicit retention job | Hospital security policy |

Why not one syslog stream for everything: syslog is clear text, its tools delete by age
and size, and its audience is IT. Clinical-AI records hold PHI, are records rather than
messages, and serve clinicians and regulators.

**The split ruling.** An inference produces two things:

| Thing | Goes to | Holds |
|---|---|---|
| Inference **metadata** line | `journald`, `LOG_CATEGORY=ai` | Event UUID, run UUID, model version, latency, status or error code |
| Inference **record** | Clinical-AI store | Caller, target pseudonym, input and output pointers, what was displayed, outcome |

## Who holds what

```
   MANUFACTURER (AI "provider")                        HOSPITAL (operator / AI "deployer" / data controller)
 ┌───────────────────────────────────────┐          ┌──────────────────────────────────────────────────┐
 │ Complaint, CAPA, vigilance files (4)  │          │ Host journald (1, 2, PHI-free part of 3)         │
 │ Aggregated performance data (3)       │ ◄─────── │   → forwarded to the central store / SIEM        │
 │ Vulnerability-investigation sets (4)  │ pseudo-  │ Clinical-AI store (3)                            │
 │ Labeling: IFU, MDS2, security manual  │ nymised  │ PACS / RIS audit trails, audit repository (2)    │
 │   → DISCLOSES capability and defaults │ excerpts │ Legal holds, incident evidence                   │
 └───────────────────────────────────────┘          └──────────────────────────────────────────────────┘
        boundary: data-processing agreement; cross-border transfer rules apply to every excerpt
```

- **Diagnostic (1)** — generated and kept on hospital machines. The manufacturer sees an
  excerpt only when the hospital exports one for a support ticket or complaint.
- **Security / audit (2)** — the hospital's evidence. The manufacturer's duty is to make
  the device able to produce it, and to say how to keep it.
- **AI inference (3)** — each party keeps the logs under its own control. On premises,
  the raw records sit with the hospital; the manufacturer's duty attaches only to what
  it actually receives.
- **QMS evidence (4)** — once an excerpt enters a quality record it is controlled by the
  manufacturer's QMS, on the QMS clock.
- **Personal data (5)** — can attach to any category. It is not a stream.

Topology changes custody mechanics, not the rule. A **single server** can host the
clinical-AI collector locally. A **client fleet** has many small journals, so forwarding
is the only way a central tier exists; treat it as an installation requirement.

## PHI rules

What counts as PHI here: patient name, patient or hospital number, national ID, accession
number, birth date, report text, image pixels or thumbnails, and **DICOM Study, Series,
and SOP Instance UIDs**. UIDs and accession numbers resolve to one patient in the PACS, so
they identify. An **unkeyed hash** of any of these also counts (Orthanc resource IDs are
one): a dictionary of patient numbers reverses it.

Not PHI: SOP Class UIDs and Transfer Syntax UIDs (the `1.2.840.10008.` root), AE titles,
model and software versions, counts, durations, status codes. AE titles and peer
addresses are site network facts: fine on site, removed from excerpts that leave it.

| ID | Rule |
|---|---|
| PHI-01 | The ops plane carries no PHI as defined above, at any log level, including debug |
| PHI-02 | Planes are correlated by event UUID and run UUID only |
| PHI-03 | Where a patient or study link is needed outside the clinical-AI plane, use a keyed hash (HMAC-SHA-256) whose key the **hospital** holds. The hospital can re-identify; the manufacturer cannot |
| PHI-04 | A PHI-pattern scan of log output runs in the automated tests, and again on staging logs before release |
| PHI-05 | PHI found in any log is a security incident: redact or purge within 30 days, find the root cause, assess breach notification. Under legal hold or inside a quality record, pseudonymise instead of deleting |
| PHI-06 | Logging by third-party components (DICOM toolkits, web servers, HTTP clients, exception reporters, inference servers) is configured and tested to the same rule — see [phi-leaks.md](phi-leaks.md) |
| PHI-07 | Local buffers that hold PHI before delivery (outbox, spool directories, core dumps) sit on an encrypted volume, mode `0600`, owned by the service user |
| PHI-08 | Any excerpt that leaves the hospital is pseudonymised first, and the transfer is covered by the data-processing agreement |

Allowed in an ops log line: event UUID, run UUID, error code, duration, queue size, DICOM
status code, SOP Class UID, AE titles, model version, a keyed-hash token (PHI-03).

```json
{"ts":"2026-11-15T03:41:07.512Z","level":"error","component":"inference",
 "event_id":"5f0c…","run_id":"a1b2…","error_code":"GPU_OOM",
 "msg":"inference failed; result not delivered","latency_ms":2210}
```

To debug one study: take the event UUID from the ops log, then look it up in the
clinical-AI store under access control. Never add an identifier "temporarily".
