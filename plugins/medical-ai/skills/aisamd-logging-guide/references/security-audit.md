# Security-audit plane — host audit, audited reads, DICOM audit messages

Three layers answer "who accessed or changed what?":

| Layer | Mechanism | Holds |
|---|---|---|
| Host | `auditd`; journal lines with `LOG_CATEGORY=audit` | Configuration and model-file changes, logins, privilege use. PHI-free |
| Clinical-AI store | Database audit, collector access log | Every read of inference records |
| DICOM | IHE ATNA audit messages to the hospital's audit record repository | Who moved or used which patient's studies. **Contains PHI by design** |

Verified 2026-11-15 against DICOM PS3.15 edition 2026d (Annex A.5–A.7), IHE ITI TF-1 ch. 9
Rev 20.0, ITI TF-2 §3.20 Rev 20.2, IHE RAD TF-3 Rev 23.0 §5.1, and RFC 5424 / 5425 / 5426
/ 9662. Grades: **P** = read in the specification text; **S** = project or vendor
documentation; **I** = this guide's interpretation, not a standard's statement.

## Requirements

| ID | Rule |
|---|---|
| SEC-01 | `auditd` watches the configuration and secrets directory and the model-weights directory |
| SEC-02 | Every read of the clinical-AI store is audited at the database level, and by the collector's own access log |
| SEC-03 | Application security events — login, logout, failed authentication, role change, configuration change, software or model version change — are logged PHI-free with `LOG_CATEGORY=audit` |
| SEC-04 | Audit data is protected: append-only, restricted access, and reading an audit log is itself an audited event |
| SEC-05 | Whether the device emits DICOM audit messages is decided explicitly with the hospital, and stated in the conformance statement: the actor claimed, the events detected, how reporting is configured, extensions, maximum message size, syslog parameters |
| SEC-06 | Audit messages use the **DICOM PS3.15 A.5.1 schema**, not the RFC 3881 schema |
| SEC-07 | Transport is syslog over TLS (RFC 5425) with octet-counted framing and a message size of at least 32,768 octets. UDP only with a written risk justification |
| SEC-08 | When the repository is unreachable, audit records are stored locally and sent later. That buffer holds PHI → PHI-07 |
| SEC-09 | Audit message content is never copied into `journald`, ops logs, or telemetry. The ops plane refers to it by event UUID |
| SEC-10 | One patient per transfer or access message; one access event per study (or per patient batch), never one per instance |
| SEC-11 | Failures are audited: TLS and peer-authentication failures, configuration changes, audit recording stopped or started, purge of locally cached studies |
| SEC-12 | `EventDateTime` carries a time zone, and the host keeps consistent time (OPS-08) |
| SEC-13 | Host security logs are forwarded to the hospital security-monitoring system where one exists |

Standard behind SEC-04: IEC 62443-4-2 CR 3.9 (protection of audit information).

## Host and store audit

```
# /etc/audit/rules.d/50-<app>.rules
-w /etc/<app>/ -p wa -k <app>_config         # configuration and secret changes
-w /opt/<app>/models/ -p wa -k <app>_model   # model weights replaced?
```

Query with `ausearch -k <app>_model -i`.

For reads of the clinical-AI database, use database-level audit (for example `pgAudit`
on PostgreSQL). A file watch on the database directory produces noise, not evidence.
Database audit can write query parameters into the server log: see [phi-leaks.md](phi-leaks.md).

## IHE ATNA in one screen

| Fact | Grade |
|---|---|
| Actors: Secure Node (secures the whole system), Secure Application (secures only itself), Audit Record Repository, Audit Record Forwarder | P |
| Both node and application **must** authenticate nodes (ITI-19) on every connection that may expose private information, and **must** record audit events (ITI-20) for all activity- and transaction-related events | P |
| Both must keep consistent time | P |
| At least one transport option is required: syslog over TLS, syslog over UDP, or FHIR feed | P |
| If the repository is unreachable, "the actor shall store the audit record locally and send it when it is able" | P |
| DICOM itself sets no trigger rule: which events fire, and when, is configurable policy. The conformance statement must say which events are detected | P |
| Neither IHE ATNA nor PS3.15 sets a retention period. ITI-20: "This transaction does not specify data retention rules" | P |
| An AI application on a hospital-managed Linux host can usually claim only **Secure Application**. An appliance whose whole stack the vendor controls could claim Secure Node | I |
| Who operates the repository is not stated by any standard. In practice the hospital's security function does; the device is configured with its address | I |

ATNA's purpose is privacy and security surveillance. IHE states it is not meant for
forensic or workflow-performance analysis, and expects products to keep a separate,
more detailed log for that. The per-inference record is that log.

## Message shape

The schema derives from RFC 3881 and has diverged from it; RFC 3881 is no longer
maintained, and validators test the DICOM schema only (P / S). Pull the exact text with
the `dicom-standard` skill: PS3.15 §A.5.1 (schema), §A.5.2 (general rules), §A.5.3 (events).

```
AuditMessage
├── EventIdentification            1     EventID (coded) · EventActionCode C/R/U/D/E
│                                        EventDateTime (with time zone) · EventOutcomeIndicator 0/4/8/12
├── ActiveParticipant              1..n  UserID · AlternativeUserID (AETITLES=AI_SCP;AI_SCU)
│                                        UserIsRequestor · RoleIDCode · network access point
├── AuditSourceIdentification      1     AuditSourceID · type code (4 = application server process)
└── ParticipantObjectIdentification 0..n patient (ID + name) · study (Study Instance UID) · query
```

- Outcome codes: 0 success, 4 minor failure, 8 serious failure, 12 major failure.
- Role codes: 110150 Application, 110151 Application Launcher, 110152 Destination,
  110153 Source.
- No empty elements and no empty-string attributes.
- A multi-homed host uses **one** network identifier in all messages.
- A process `UserID` should be an identifier that also appears in local system logs, so
  the audit trail can be matched to them.

## Events for a PACS-connected AI application

Event codes are DCM codes (P). Who emits each event is a system-design question that
DICOM leaves open; the assignments below follow the IHE Radiology patterns where one
exists (P) and are marked **I** where they are this guide's reading.

| Event (code) | Trigger | Receiving auto-routed studies (C-STORE SCP) | Sending results back (SCU) | DICOMweb client |
|---|---|---|---|---|
| Application Activity (110100) | Service start / stop | Yes — required of every secure application | Yes | Yes |
| Begin Transferring DICOM Instances (110102) | Intent to send | No; the sender audits | **Yes**, before C-STORE | **Yes**, before STOW-RS |
| DICOM Instances Transferred (110104) | Transfer complete | **Yes**, per study received (action C) | Optional; IHE assigns it to the receiver | Assigned to the receiving or serving side |
| DICOM Instances Accessed (110103) | Instances viewed or used | When the model reads the study for inference (action R) — I | — | **Yes**, after a WADO-RS retrieve; also after C-MOVE of priors |
| Query (110112) | A query is issued | Only as a C-FIND SCP | — | The **responder** must report; client logging is optional |
| DICOM Study Deleted (110105) | Whole study deleted | **Yes**, when the local cache purges a study — I | Same | Same |
| Security Alert (110113) | Node-authentication failure (110126), security configuration (110129), software configuration (110131), audit recording stopped / started (110133 / 110134) | Report failures | Same | Same |
| User Authentication (110114) | Login or logout attempt | Only if the application has an interactive login | Same | Same |
| Audit Log Used (110101) | Someone reads an audit log | When an operator reads the local audit buffer | Same | Same |
| Export (110106) / Import (110107) | Data leaves or enters the security domain | Not for in-domain PACS traffic. Use for de-identified research exports or copies to an external store — I | Same | Same |

- A partial delete is **Instances Accessed** with action D, not Study Deleted.
- Query records the request, not the response. The message holds the **full query data
  set**, base64-encoded.
- Reporting every successful node authentication floods the repository; report failures.
- A model or software version change fits Security Alert 110131 "Software Configuration" — I.
- The IHE Radiology table that maps "Instances-Stored" has known internal citation
  errors in Rev 23.0; receivers should accept either Begin Transferring or Instances
  Transferred for it (P).

## PHI in audit messages

By design, transfer, access, delete, export, and import messages carry **patient ID and
patient name as mandatory fields**, plus the Study Instance UID, and optionally the
accession number and SOP Instance UIDs. Query messages carry the query data set, which
can hold patient-matching keys. All carry user names, AE titles, host names, and IP
addresses (P).

So:

- The full message belongs in the hospital's repository and in the device's local
  store-and-forward buffer. Nowhere else (SEC-09).
- IHE calls the repository a "high value target" whose store "should be protected
  accordingly" (P).
- Leave out details that do not matter, "especially if they would reveal PHI" (P).
- No standard requires tamper evidence for the audit trail (P, by absence). One
  open-source repository stack keeps a hash tree over messages (S).

## Transport

| Topic | Fact | Grade |
|---|---|---|
| Preferred | Syslog over TLS, RFC 5425, port 6514, mutual certificate authentication | P |
| TLS version | 1.2 required, 1.3 preferred when present (RFC 9662 updates RFC 5425) | P |
| Framing | **Octet counting**: `MSG-LEN SP SYSLOG-MSG`. Not line-feed framing | P |
| Size | RFC 5425 requires 2,048 octets. **DICOM requires ≥ 32,768.** Oversize messages may be dropped or truncated silently | P |
| UDP | RFC 5426, port 514. No acknowledgement, no confidentiality; truncation corrupts the XML. IHE allows it only when a risk analysis justifies it | P |
| Priority | Facility 10, severity 5 → `<85>` | P |
| `MSGID` | `IHE+RFC-3881` (IHE) or `DICOM+RFC3881` (DICOM); must be set | P |
| Byte-order mark | RFC 5424 says UTF-8 content must start with one; IHE says it is "discouraged, but acceptable". Test against the actual repository | P |
| FHIR feed | HTTP POST of a FHIR R4 `AuditEvent`. **Trial implementation** status | P |
| Retired | Reliable syslog (RFC 3195), the "ATNA Encryption" option, TLS 1.0 floors | P |

## Implementation options on Linux

| Option | Gives | Grade |
|---|---|---|
| dcm4che 5 (Java) | Audit modules, a `syslog` sender tool, and `syslogd`, usable as a local test repository. Actively released | P |
| dcm4chee-arc with an Elastic stack | A reference repository | S |
| IPF `ipf-commons-audit` (Java) | Builders for the PS3.15 events; UDP, TLS syslog, and FHIR transports. Store-and-forward is yours to build | S |
| Python | No maintained DICOM-audit library was found. Generate the XML, validate it against the A.5.1 schema, send through a TLS syslog relay | S (absence) |
| .NET | The one library found is stale (last change 2020) | S |
| `rsyslog` as relay | `omfwd` with a TLS stream driver. **Two defaults break conformance:** `TCP_Framing` is `traditional` — set `octet-counted`; `maxMessageSize` is 8K — raise it to at least 32768 | P |

## Do not duplicate the clinical-AI record

| | DICOM audit message | Per-inference record |
|---|---|---|
| Question | Who touched which patient's data, from where? | What did the model see and say, and was it right? |
| Consumer | Hospital security reviewers | Clinical safety, ML team, post-market surveillance |
| Unit | Per transfer, access, or study; may summarise | One per model invocation |
| Model data | None | Model version, inputs, outputs, outcome |

- Never put model outputs or scores in an audit message.
- Never present the inference records as the hospital's audit trail.
- To join the two, add an implementation-defined `ParticipantObjectDetail` that carries
  the inference event UUID. The schema allows it; no IHE convention exists — I.

## Mistakes seen in small-vendor implementations

1. The RFC 3881 schema used in place of the DICOM schema.
2. Line-feed TCP framing (the `rsyslog` default) in place of octet counting.
3. Buffers below 32,768 octets, which truncate large transfer and query messages silently.
4. UDP by default.
5. No local store-and-forward.
6. `EventDateTime` without a time zone.
7. Several patients in one transfer or access message; one message per instance.
8. Audit XML, with the patient name in it, copied into the journal.
9. No audit of TLS failures, configuration changes, or cache purges.
10. A conformance statement that omits the audit content.

## Not verified

- Audit requirements in the IHE Radiology AI Results and SOLE supplements were not read.
- Whether `pynetdicom` or `fo-dicom` offer any audit support (none was found).
- Whether Python's standard `SysLogHandler` can produce RFC 5424 with octet counting.
  Assume it cannot until tested.
- TLS 1.3 defaults in `rsyslog` and dcm4che.
