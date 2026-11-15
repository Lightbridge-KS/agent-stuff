# Design, analyse, disclose — the working procedures

## Design a logging system

1. Settle the inputs in `SKILL.md` ("Establish these first").
2. Settle the open questions below. They belong to the product owner and the hospital;
   present options and a recommendation, then record the answer.
3. Draw the three planes for this product: what each one stores, where, and who holds it.
4. Choose retention per category with [retention.md](retention.md), step by step.
5. Write the result into the project's design documents, citing requirement IDs. A
   decision that departs from an ID states why.
6. Phase the work. Phase 1: ops plane, PHI rules, start and output events, outbox.
   Phase 2: artifact capture policy, outcome linkage, feedback, central forwarding.

### Open questions

| # | Question | Sets |
|---|---|---|
| 1 | Trigger modes: auto-route, on-demand, or both? | Caller type and ID |
| 2 | PACS interface: DIMSE, DICOMweb, or both? | Pointer scheme; leak surface |
| 3 | What does the clinician see? | Output type and summary |
| 4 | Can the system know when a result was *viewed*? | Timing of the output event (CAI-12) |
| 5 | How are final reports obtained, and who judges agreement: a rule, a parser, a clinician? | Outcome linkage (CAI-18) |
| 6 | Who holds the pseudonym key and the re-identification map? | PHI-03, CAI-08 |
| 7 | Where does the collector run, and on which database? | CAI-17 |
| 8 | Capture policy: sampling rate and risk triggers? | CAI-19 |
| 9 | Failure representation: ops-line correlation only, or an artifact event as well? | CAI-13 |
| 10 | Will the collector accept the extension object, and which fields go in it? | CAI-10 |
| 11 | Does a hospital central log store exist? Who forwards, who stores, who monitors the floor? | RET-01, RET-08 |
| 12 | Does the hospital require DICOM audit messages to an audit record repository? | SEC rules |
| 13 | What is the device lifetime *L*, per version or per product family? | RET-04, RET-12 |
| 14 | Who reviews which events, how often, and how do findings reach CAPA and change control? | CAI-24 |

## Analyse an existing system

1. Map the code: where studies enter, where the model is invoked, where results are
   published. Name the chokepoint, or state that none exists.
2. List every log sink: stdout, files, journal fields, databases, third-party agents,
   HTTP access logs, error reporters. Include libraries (PHI-06).
3. For each sink, record the plane, the category, and the PHI it can carry.
4. Walk the five requirement tables. One row per ID.
5. Run a PHI-pattern scan on real log output from a test run with synthetic data
   ([phi-leaks.md](phi-leaks.md)).
6. Report the gap table, ordered: invariant violations first, then PHI, then retention.

Gap table shape:

| ID | Status | Evidence | Gap | Fix |
|---|---|---|---|---|
| PHI-01 | Fail | `router/store.py:88` logs `ds.StudyInstanceUID` at INFO | UID in the ops plane | Log the event UUID; drop the UID |
| OPS-04 | Unknown | No journald drop-in in the repository | Floor not engineered | Add the drop-in; measure volume |

Status values: `Pass`, `Fail`, `Partial`, `Unknown`, `N/A`. `Unknown` is a finding. Give
`file:line` or a command output as evidence; a claim without evidence is `Unknown`.

## Pitfalls

| Trap | Correct behaviour |
|---|---|
| A Study UID or patient number in an ops log "for debugging" | Log the event UUID; look the study up in the clinical-AI store |
| `MaxRetentionSec=90d` to "guarantee 90 days" | It caps at 90 days. Size the journal, set the cap above the floor, monitor |
| Trusting the default journal on a small disk | The 4 GB default cap can hold days, not months, under study load |
| Rotating clinical-AI records with `logrotate` | An explicit retention job |
| Treating `LOG_CATEGORY=ai` journal lines as the inference record | The record lives in the clinical-AI store |
| A logging failure fails the inference | Outbox, retry, inference proceeds |
| Retrying a `400` forever | Park it and alert |
| Logging the raw score only | Log what was displayed, plus the triage flag |
| Running outcome linkage on AI-positive studies only | False negatives become invisible |
| Editing an outcome | Post a new event; records are write-once |
| Watching the database directory with `auditd` to audit reads | Use database-level audit; file watches are noise |
| Copying a host excerpt into a complaint file unredacted | Pseudonymise; it is now a long-lived quality record |
| Quoting "the law requires 90 days" | No single rule says so. Cite the instrument and its condition |
| Assuming the EU AI Act log floor applies today | It starts on the application date in the register |
| One retention number for all logs | Retention is per category and per party |
| Leaving toolkit debug logging on in production | See [phi-leaks.md](phi-leaks.md) |

## Manufacturer duties: disclosure

The manufacturer must tell the hospital what the device logs and keeps. Three places.

**Instructions for use / security manual.** Template; fill the brackets:

> *"[Product] records operational and security-audit events, and PHI-free metadata of
> each AI inference, to the Linux systemd journal. Inference records are kept in a
> separate clinical-AI event store. The default configuration retains at least 90 days of
> journal events locally, subject to available disk space (configured limit: [X] GB).
> [Product] does not by itself guarantee long-term retention. The operator is responsible
> for forwarding logs to a central log store and for retaining them in accordance with
> applicable law and the operator's policies. The manufacturer recommends at least
> 13 months of searchable retention for audit and AI-inference events. Journal entries are
> designed not to contain direct patient identifiers; if personal data is found in a log,
> report it to the manufacturer as a security incident. Forward Secure Sealing is enabled;
> keep the verification key off the device."*

Add the jurisdiction sentence that applies (for example the EU deployer duty) from the
register, with its application date.

**MDS2, audit-controls section.** Answer: events logged; timestamps and time
synchronisation; export format; integrity protection; local storage capacity in days at
typical load; forwarding protocols; default local and recommended central retention.

**Agreements with the hospital.**

- Data-processing or data-sharing agreement: roles per data flow, data categories and
  the pseudonymisation method, retention per category, cross-border transfer basis,
  breach-notification time.
- Log-access clause: the hospital preserves and exports the relevant log range within
  an agreed number of working days of a request tied to a complaint or incident, and
  places a legal hold.
- Responsibility agreement (IEC 80001-1): who forwards, who stores, who monitors the floor.

## Manufacturer duties: QMS text

Requirement text that a software development plan and a security plan can adopt. Adapt
names and numbering to the project's QMS.

| Topic | Requirement text | IDs |
|---|---|---|
| Categories | Every log entry shall carry `LOG_CATEGORY` with one of `diag`, `audit`, `ai`. QMS evidence is not emitted by the device; it is created when an excerpt is attached to a quality record | OPS-02 |
| Content | Log entries shall not contain direct patient identifiers or DICOM Study, Series, or SOP Instance UIDs in clear text. Automated tests shall include a PHI-pattern scan of log output | PHI-01, PHI-04 |
| Local retention | The installer shall configure persistent journal storage sized to retain ≥ 90 days at the 95th-percentile measured volume, with capacity and forwarding-lag alarms | OPS-03 to OPS-06 |
| Forwarding | The software shall support forwarding by `systemd-journal-upload` (TLS) and syslog (RFC 5424 over TLS) | OPS-09 |
| Verification | A daily self-check shall record the timestamp of the oldest local entry and warn when the floor is not met | OPS-05 |
| Record retention | Quality records, including log excerpts, shall be retained per RET-04. Records under legal hold shall not be disposed of | RET-04, RET-06 |
| Disclosure | Logging capability, default retention, and recommended retention shall be disclosed in the instructions for use and MDS2 | RET-09 |
| Incident | Discovery of personal data in any log shall be handled as a security incident | PHI-05 |
| Review | The retention schedule shall be reviewed yearly | RET-11 |

## Standards a logging design supports

Pointers for the quality and regulatory owner; this guide does not interpret them.

- ISO 13485 and ISO 14971 — post-market surveillance and production/post-production
  information. Outcome and feedback events are evidence.
- IEC 62304 — maintenance and problem resolution. Link each problem report to event
  UUIDs and `model_version`.
- IEC 81001-5-1 and IEC 62443-4-2 — security lifecycle and audit capability.
- IEC 80001-1 — the hospital's risk management of the connected system.
