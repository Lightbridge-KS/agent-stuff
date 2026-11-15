# Regulatory register — what the law and the standards say about log retention

**Status date: 2026-11-10.** Compiled from one research briefing; no fact was re-verified
after that date. This is engineering reference, **not legal advice**. Before a number from
this file goes into a QMS record, labeling, or a submission, re-check it against the
primary text and have the QA/RA owner confirm it.

Evidence grade on every row:

| Grade | Meaning |
|---|---|
| **P** | A specific provision of a statute, regulation, or standard; the briefing quoted or cited the provision itself |
| **S** | Known only through secondary reporting (law-firm notes, consultancy and vendor articles) |
| **V** | Not confirmed against any text. Treat as an open question, never as a fact |

The one-line summary: **no jurisdiction sets one retention number for medical-device
software logs.** The hard numbers come from adjacent regimes (computer-crime law, QMS
record rules, the EU AI Act). Most security standards require the *capability* to log and
the *disclosure* of what is kept, and set no period.

## Thailand

| Instrument | What it says | Number | Grade |
|---|---|---|---|
| Computer Crime Act B.E. 2550 (am. B.E. 2560) s.26 | A *service provider* must retain computer traffic data from the date it enters the system; an official may order longer, case by case. Fine up to THB 500,000 | **≥ 90 days**; up to **2 years** by order | P |
| MDES Notification on traffic-data retention B.E. 2564 (in force 14 Aug 2021) | Defines "service provider": one who gives *others* internet or computer-mediated communication, or stores computer data for others. The listed duty-holders provide service "to the general public" | — | S |
| Same, applied to a hospital | Internal staff networks probably fall outside; patient or guest Wi-Fi and hosted portals could bring a hospital in. **Unsettled** | — | V |
| Same, applied to an on-premises software vendor | Not a service provider. Becomes one if it hosts a cloud service that stores data for hospitals | — | S |
| Cybersecurity Act B.E. 2562 s.49 | Public health is a critical information infrastructure (CII) sector | — | P |
| CII Code of Practice and Standard Framework B.E. 2564, cl. 22.1.3 | Keep "logs of all access and all attempts to access critical services" and review them regularly | **None** | P |
| CII duties notification (effective 20 Jun 2024) | Report incidents to the regulator within 24 hours; cooperate in evidence collection. Implies logs must survive long enough to be preserved | — | S |
| NCSC Minimum Standard for Data/Information Systems B.E. 2566 | Not reviewed; may contain a logging control | Unknown | V |
| Medical Device Act and Thai FDA SaMD/AI guidance | Secure design, security documentation for users, risk management, incident response. No log period | **None** | S |
| MOPH Notification on records and reports for manufacture, import and sale (effective 1 Mar 2026) | Licensee records, and complaint records under a separate notice | **≥ 5 years** | S |
| MOPH Notification on malfunctions and adverse events (2020) | Report: serious public-health threat 48 h; death or serious injury 10 days; possible recurrence 30 days | — | S |
| PDPA B.E. 2562 s.37(3), s.39, s.40, ss.28–29 | Erase or anonymise when no longer necessary; state the retention period in the record of processing; processors act on documented instructions; cross-border safeguards. Health data is sensitive personal data | **Ceiling**, no floor | P |
| Hospital accreditation / medical-record rules | No audit-trail retention period was found | Unknown | V |

Practice note: Thai organisations widely treat 90 days as the default. The "CII must keep
logs 90 days" claim in vendor material traces back to the Computer Crime Act or to
individual agencies' own codes, not to a national cybersecurity rule (S).

Whether a given hospital is a designated CII is not generally published. Ask the
hospital's security officer; do not assume.

## United States

| Instrument | What it says | Number | Grade |
|---|---|---|---|
| QMSR, 21 CFR Part 820 (effective 2 Feb 2026) | Incorporates ISO 13485:2016, so §4.2.5 governs quality-record retention | **≥ device lifetime as defined by the manufacturer, and ≥ 2 years from release** | P |
| 21 CFR 820.35(a) | Complaint-record content: review, investigation, device name, date, UDI, details. Log excerpts that support an investigation belong here | — | P |
| 21 CFR 803.18 | Medical-device-report event files | **2 years from the event, or the expected device life, whichever is greater** | P |
| 21 CFR 803 deadlines | 30 calendar days; 5 work days when remedial action is needed | — | P |
| 21 CFR 806.20 | Records of unreported corrections and removals | 2 years beyond expected life (exact wording unconfirmed) | V |
| FD&C Act §524B + FDA premarket cybersecurity guidance (final; re-issued 3 Feb 2026) | "Event detection and logging are critical capabilities that should be present in a device and the larger system in which it operates." Labeling must let users operate the device securely | **None** | P (statute) · S (guidance version) |
| HIPAA 45 CFR 164.312(b) | Audit controls: mechanisms that "record and examine activity" | **None** | P |
| HIPAA 45 CFR 164.316(b)(2)(i) | *Documentation* kept 6 years. Whether raw audit logs are "documentation" is contested; conservative practice keeps audit-log **review records** and incident evidence 6 years, not every raw event | 6 years (scope contested) | P (text) · V (scope) |
| HIPAA Security Rule NPRM (Jan 2025) | Not final at the status date; final action reported as moved to July 2027 | — | S |
| 21 CFR 11.10(e) | Audit trails kept "at least as long as that required for the subject electronic records". Applies to the manufacturer's eQMS, not to operational device logs | Inherits | P |
| FDA draft guidance, AI-enabled device software functions: lifecycle management (Jan 2025) | Recommends postmarket performance monitoring. Still draft at the status date | **None** | S |

HIPAA applies only when a US customer is a covered entity and the manufacturer handles
ePHI as its business associate.

## European Union

| Instrument | What it says | Number | Grade |
|---|---|---|---|
| MDR 2017/745 Art. 10(8) | Keep technical documentation, declaration of conformity, certificates. Post-market surveillance documentation sits inside the technical documentation | **≥ 10 years after the last device is placed on the market** (15 for implantables) | P |
| MDR Art. 87 | Vigilance: serious incident 15 days; serious public-health threat 2 days; death or unanticipated serious deterioration 10 days | — | P |
| MDCG 2019-16 rev.1 | Tell operators about the logging function, "particularly the medical device's log storage capacity", and logging parameters | **None** | P |
| AI Act 2024/1689 Art. 12 | A high-risk system must technically allow automatic recording of events over its lifetime | — | P |
| AI Act Art. 19(1) (provider) and Art. 26(6) (deployer) | Each keeps the automatically generated logs **under its control** for a period appropriate to the intended purpose, unless other Union or national law (notably data protection) provides otherwise | **≥ 6 months** | P |
| AI Act Art. 18 | Provider documentation | **10 years** after placing on the market | P |
| AI Act application date for product-embedded (Annex I, incl. MDR devices) high-risk systems | Moved to **2 Aug 2028** by Regulation (EU) 2026/1744 (the "Digital Omnibus on AI"); was 2 Aug 2027 | — | S |
| Same regulation, sectoral-equivalence mechanism | The Commission may limit some AI Act obligations where sectoral law gives equivalent protection. Final text for Annex I not confirmed | — | V |
| MDCG 2025-6 / AIB 2025-1 | A device AI system is high-risk when it is a safety component or itself a device **and** needs notified-body assessment (MDR Class IIa and above). Integrate AI Act logging into the MDR QMS | — | S |
| GDPR Art. 5(1)(e), Art. 28, Ch. V | Storage limitation; processor terms; transfers. No adequacy decision for Thailand was identified (V) | **Ceiling**, no floor | P |
| NIS2 Directive 2022/2555 Art. 21 | Risk-management measures including logging, as each Member State implements them. Healthcare providers are in scope; a non-EU manufacturer's position is unclear | None EU-wide | P (text) · V (applicability) |
| Cyber Resilience Act 2024/2847 Art. 2(2) | Excludes products covered by the MDR/IVDR | Not applicable | P |

## Standards — capability, not periods

| Standard | Requires | Retention number? |
|---|---|---|
| ISO 13485:2016 §4.2.4–4.2.5 | Document and record control | **Yes:** ≥ device lifetime as defined, ≥ 2 years from release |
| IEC 62304 §6, §9 | Maintenance plan; problem-resolution records | No (records fall under the QMS rule) |
| IEC 81001-5-1:2021 | Security lifecycle; security documentation for operators, including logging capability | No |
| IEC 62443-4-2 CR 2.8 / 2.9 / 2.10 / 3.9 | Auditable events; audit storage capacity; response to audit-processing failure; protection of audit information | No (capacity must be "sufficient"; alert near the limit) |
| IEC 80001-1:2021 | Hospital-side risk management of connected systems; responsibility agreements | No |
| ISO/IEC 27001:2022 A.8.15 | Produce, store, protect, and analyse logs | No (organisation-defined) |
| MDS2 (2019), AUDT section | The manufacturer *discloses* audit capability, events, export, and storage | No (disclose your value) |
| IHE ATNA / DICOM PS3.15 | Audit message format, secure transport, audit record repository — see [security-audit.md](security-audit.md) | No |
| NIST SP 800-53 Rev.5 AU-11 | "Retain audit records for [organisation-defined time period]" | No (parameterised) |

All grade P for "no number", except IEC 62304 and IEC 81001-5-1 (S: clause-level reading
not confirmed).

What these standards do fix: the manufacturer owns **capability** (events, timestamps,
integrity, capacity, failure alarms, export) and **disclosure** (what the device keeps by
default). The hospital owns the retention decision.

## Numeric benchmarks and latency evidence

Use these to argue for a window when no law sets one.

| Source | Figure | Grade |
|---|---|---|
| CIS Controls v8, Safeguard 8.10 | Retain audit logs ≥ 90 days | P |
| PCI DSS v4.0, Req. 10.5.1 | ≥ 12 months, most recent 3 months immediately available | P |
| OMB M-21-31 (2021) | 12 months active + 18 months cold. **Rescinded 22 May 2026** by M-26-14 | S |
| OMB M-26-14, Appendix B | Actively searchable ≥ 6 months, retrievable for 1 year | S |
| NIST SP 800-92 (2006); Rev.1 still an initial public draft | Planning guidance, no fixed number | P |
| Mandiant M-Trends 2026 | Global median dwell time 14 days; 122 days for espionage cases; 393 days average for one long-dwell backdoor family, with the remark that "standard 90-day log retention leaves organizations unable to identify the initial access vector" | P |
| IBM Cost of a Data Breach 2025 | Healthcare breaches took **279 days** to identify and contain (global average 241) | P |
| IBM Cost of a Data Breach 2026 | Global average 247 days; no healthcare lifecycle figure found | S |

Complaint latency matters as much as intrusion latency. Vigilance clocks start at
*awareness*, and radiology AI errors are often found retrospectively (discrepancy review,
peer review, a later study) — plausibly 6–12 months after the event. A 90-day local log
has usually rotated by then.

## Watch-list — facts expected to move

Re-check these before relying on them; update the status date when you do.

| Item | State at the status date | Why it matters |
|---|---|---|
| EU AI Act, Annex I high-risk application date | 2 Aug 2028 (S) | Starts the 6-month floor for provider and deployer |
| EU AI Act, obligations limited for MDR devices | Unconfirmed (V) | Could remove or soften Art. 12/19/26 duties |
| HIPAA Security Rule final rule | Proposed; final targeted July 2027 (S) | May add explicit logging duties |
| FDA AI-enabled device lifecycle guidance | Draft (S) | May state monitoring-data expectations |
| Thai PDPA amendment and PDPC AI guidance | Not verified (V) | May change the ceiling logic |
| Thai NCSC Minimum Standard B.E. 2566 | Not reviewed (V) | May hold a numeric log period for CII |
| NIST SP 800-92 Rev.1 | Draft (P) | Successor planning guidance |
| M-Trends and IBM annual reports | 2026 / 2025 editions | The "optimal window" argument rests on them |

## Questions that belong to counsel, not to the agent

Surface these; never settle them in code or in a design document.

1. Is the deploying hospital a "service provider" under the Thai traffic-data rule? Is the manufacturer one, if it hosts any cloud component?
2. Is the deploying hospital a designated CII, and does its regulator set a numeric log period?
3. For each data flow (support excerpts, telemetry, performance datasets): is the manufacturer a processor or an independent controller, and what is the cross-border transfer basis?
4. Does the HIPAA 6-year rule cover raw audit logs for a given US customer?
5. What is the device lifetime *L*, and does it run per major version or per product family?

## Primary sources

- Thai Computer Crime Act (No. 2): <https://www.dga.or.th/wp-content/uploads/2016/12/file_ce8c32197b28a5d438136a3bd8252b7c.pdf>
- Thai Cybersecurity Act B.E. 2562: <https://www.ratchakitcha.soc.go.th/DATA/PDF/2562/A/069/T_0020.PDF>
- Thai CII Code of Practice B.E. 2564: <https://ratchakitcha.soc.go.th/documents/17176753.pdf>
- 21 CFR 820.35: <https://www.law.cornell.edu/cfr/text/21/820.35>
- MDCG 2019-16 rev.1: <https://health.ec.europa.eu/document/download/b23b362f-8a56-434c-922a-5b3ca4d0a7a1_en>
- NIST SP 800-92 Rev.1 (draft): <https://csrc.nist.gov/pubs/sp/800/92/r1/ipd>
- M-Trends 2026, executive edition: <https://cloud.google.com/security/resources/m-trends-executive-edition>
- EU regulations (MDR 2017/745, AI Act 2024/1689, GDPR, NIS2, CRA): EUR-Lex, by regulation number
- US regulations (21 CFR 803, 806, 820, Part 11; 45 CFR 164): eCFR, by citation
