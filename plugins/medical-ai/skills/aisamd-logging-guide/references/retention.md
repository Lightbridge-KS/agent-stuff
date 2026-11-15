# Retention — floors, ceilings, and the proposed windows

The periods here are a **proposed default**, argued from the facts in
[regulatory-register.md](regulatory-register.md). They are not a legal minimum and not
legal advice. The hospital owns the final retention decision; the manufacturer's quality
and regulatory owner owns the QMS-evidence rule.

## The shape of the answer

```
              FLOOR (strongest legal minimum,          CEILING (data-protection storage
              investigation latency, dwell time)       limitation, cost, breach blast radius)
                     │                                          │
 0d ───── 90d ────── 6mo ──────── 13mo ──────────── 24mo ───────┴────── device lifetime / 10 y
          │          │            │                 │                   │
     host journald   EU AI Act    central store     cold archive        QMS evidence
     hot tier        6-month      searchable        (security and AI)   (quality records)
                     floor
```

- **90 days** covers the median intrusion and a fast complaint. It is a floor for the
  host, not a target for the system.
- **13 months** covers one full annual review cycle plus a month of overlap, and exceeds
  the 279-day healthcare breach lifecycle and the EU AI Act's 6-month floor.
- **24 months** equals the longest period a Thai official can order under the Computer
  Crime Act, and catches most long-dwell intrusions.
- Beyond 24 months the forensic value falls while data-protection risk keeps rising.
  That is the ceiling for anything that is not a quality record.

## Requirements

| ID | Rule |
|---|---|
| RET-01 | Tiered default: host ≥ 90 days hot; central store 13 months searchable; cold archive to 24 months for security/audit and AI-inference logs; then delete |
| RET-02 | Diagnostic logs: ≥ 90 days on the host, ≤ 13 months centrally, then delete |
| RET-03 | AI-inference records: 13 months raw at the hospital, pseudonymised at source. A raw feed received by the manufacturer: ≤ 13 months. Derived performance datasets and analyses are quality records (RET-04) |
| RET-04 | A log excerpt attached to a complaint, CAPA, nonconformity, or vigilance record is a quality record. Keep it until the **later** of (a) release date + device lifetime *L* + 2 years and (b) 10 years after the last unit of that version is placed on the EU market. Where Thai licensee rules apply, not less than 5 years |
| RET-05 | Personal data creates no floor of its own. It inherits the floor of its category and imposes the ceiling: shortest necessary |
| RET-06 | A legal hold overrides every deletion rule, and is recorded |
| RET-07 | Clinical-AI records are deleted only by an explicit, documented retention job — never by `logrotate` or journal vacuum |
| RET-08 | Every event that may matter later reaches the central store, or an exported excerpt, **before** the host tier rotates it. A 90-day host log alone will often be gone when a retrospective complaint arrives |
| RET-09 | The manufacturer discloses the default local retention and the recommended central retention in the instructions for use and in MDS2 |
| RET-10 | Deletion at the ceiling is implemented and verified, not only written in a policy |
| RET-11 | The schedule is reviewed yearly against the watch-list in the regulatory register |
| RET-12 | Device lifetime *L* is defined per released major version in the device master file. RET-04 cannot be evaluated without it |
| RET-13 | Vulnerability-investigation material (forensic log sets, exploit analyses) is a quality record under RET-04 |

## Matrix: category × party

**M** = mandated floor · **C** = ceiling · **O** = proposed optimal. Grades and exact
citations are in the register.

| Category | Party | Thailand | US | EU | **O** |
|---|---|---|---|---|---|
| 1 Diagnostic | Hospital | M: 90 d only if the logs are "traffic data" *and* the hospital is a "service provider" (unsettled). C: PDPA | M: none | M: none. C: GDPR | Host ≥ 90 d; central 13 mo; delete |
| 1 Diagnostic | Manufacturer | M: none | same | same | Support-ticket copies ≤ 13 mo unless they become category 4 |
| 2 Security / audit | Hospital | M: 90 d (+ up to 2 y by order) if a service provider; CII code: keep and review, no number | M: audit *controls*, no number; 6 y for documentation (scope contested) | M: AI Act ≥ 6 mo for AI-system logs, from 2 Aug 2028; NIS2 national rules | Host 90 d; central 13 mo; archive to 24 mo; 6 y for US audit-review records |
| 2 Security / audit | Manufacturer (its own cloud, update, or remote-support services) | M: 90 d if it stores data for others | Capability | M: AI Act ≥ 6 mo for logs under its control | 13 mo searchable + archive to 24 mo |
| 3 AI inference | Hospital (deployer) | M: none numeric. C: PDPA | M: none numeric | **M: ≥ 6 mo, from 2 Aug 2028.** C: GDPR | 13 mo raw, pseudonymised at source |
| 3 AI inference | Manufacturer (provider) | Post-market duty, no number | Monitoring expected, no number | M: ≥ 6 mo for logs under its control; MDR post-market surveillance | Raw feed ≤ 13 mo; derived datasets = category 4 |
| 4 QMS evidence | Manufacturer | M: ≥ 5 y (licensee and complaint records) | M: ≥ lifetime, ≥ 2 y from release | M: ≥ 10 y after the last device is placed on the market | **max(release + *L* + 2 y, last EU placing + 10 y)** |
| 5 Personal data | Both | C: PDPA s.37(3) | C: minimum necessary | C: GDPR Art. 5(1)(e) | Do not log; if leaked, purge or redact ≤ 30 d; pseudonymise inside category 4 |

## How to choose for a given product

1. Take the markets from the inputs in `SKILL.md`. Drop the columns that do not apply.
2. For each category, the floor is the **largest** applicable M. If no M applies, the
   floor is the latency argument (90 days host, 13 months central).
3. The ceiling is the data-protection rule, unless the data is a quality record.
4. If the hospital has no central store, the 13-month and 24-month tiers do not exist.
   Then either the device keeps AI-inference records in its own size-budgeted store with
   its own retention job, or forwarding becomes an installation requirement. Choose one
   and write it down.
5. Hand the unsettled items (register, "Questions that belong to counsel") to the
   product owner. Do not resolve them by picking a number.

## Why an excerpt changes clock

A host log line is transient operational data. The same line copied into a complaint
investigation is evidence in a controlled quality record. Its retention is then the QMS
record rule, which runs for years, and its personal data must be pseudonymised because
the ceiling logic no longer deletes it. Design the export path with that in mind: an
export tool that pseudonymises, records the time range and the event UUIDs, and hashes
the excerpt.
