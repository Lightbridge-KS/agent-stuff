# Endpoint Index

Lookup table for resolving the exact path + method for a task. Methods are listed
as the verbs each path supports. `{id}` is an **Orthanc ID** unless noted.

This is curated from the Orthanc REST cheat sheet. For the always-current,
fully-parameterized spec, see the OpenAPI docs at <https://orthanc.uclouvain.be/api/>.

- **Tier 1 — Core** below covers the ~90% of real work. Start here.
- **Tier 2 — Appendix** at the end lists the long tail (attachments, metadata,
  labels, per-frame variants, log levels, server-config knobs).

---

## Tier 1 — Core

### System, statistics & tools

| Path | Methods | Summary |
| --- | --- | --- |
| `/system` | GET | Server info & version (check before version-gated calls) |
| `/statistics` | GET | Database-wide statistics |
| `/changes` | GET, DELETE | List / clear the changes log |
| `/exports` | GET, DELETE | List / clear the exported-resources log |
| `/tools/find` | POST | Search the LOCAL database (see data-access.md) |
| `/tools/lookup` | POST | Resolve a DICOM UID → Orthanc ID(s) |
| `/tools/count-resources` | POST | Count local resources matching a query |
| `/tools/create-dicom` | POST | Create one DICOM instance (e.g. from PDF/PNG) |
| `/tools/create-archive` | GET, POST | Build a ZIP of an arbitrary resource set |
| `/tools/create-media` | GET, POST | Build a DICOMDIR media ZIP |
| `/tools/bulk-anonymize` | POST | Anonymize a set of resources |
| `/tools/bulk-modify` | POST | Modify a set of resources |
| `/tools/bulk-delete` | POST | Delete an unrelated set of resources (≥ 1.9.4) |
| `/tools/bulk-content` | POST | Describe a set of resources |
| `/tools/generate-uid` | GET | Generate a DICOM UID |
| `/tools/labels` | GET | All labels in use |
| `/tools/now`, `/tools/now-local` | GET | Server time (UTC / local) |
| `/tools/reset` | POST | Restart Orthanc |
| `/tools/shutdown` | POST | Shut Orthanc down |

### Patients

| Path | Methods | Summary |
| --- | --- | --- |
| `/patients` | GET | List patient IDs (`?expand` for details) |
| `/patients/{id}` | GET, DELETE | Get / delete a patient (cascades) |
| `/patients/{id}/studies` | GET | Child studies |
| `/patients/{id}/anonymize` | POST | Anonymize patient |
| `/patients/{id}/modify` | POST | Modify patient |
| `/patients/{id}/archive` | GET, POST | ZIP of the patient |
| `/patients/{id}/statistics` | GET | Patient statistics |

### Studies

| Path | Methods | Summary |
| --- | --- | --- |
| `/studies` | GET | List study IDs (`?expand` for details) |
| `/studies/{id}` | GET, DELETE | Get / delete a study |
| `/studies/{id}/series` | GET | Child series |
| `/studies/{id}/instances` | GET | Child instances |
| `/studies/{id}/instances-tags` | GET | Tags of all child instances |
| `/studies/{id}/shared-tags` | GET | Tags common to all children |
| `/studies/{id}/anonymize` | POST | Anonymize → new study |
| `/studies/{id}/modify` | POST | Modify study |
| `/studies/{id}/merge` | POST | Merge another study into this one |
| `/studies/{id}/split` | POST | Split series/instances into a new study |
| `/studies/{id}/archive` | GET, POST | ZIP (POST for async job) |
| `/studies/{id}/media` | GET, POST | DICOMDIR media ZIP |
| `/studies/{id}/statistics` | GET | Study statistics |
| `/studies/{id}/patient` | GET | Parent patient |

### Series

| Path | Methods | Summary |
| --- | --- | --- |
| `/series` | GET | List series IDs (`?expand` for details) |
| `/series/{id}` | GET, DELETE | Get / delete a series |
| `/series/{id}/instances` | GET | Child instances |
| `/series/{id}/study`, `/series/{id}/patient` | GET | Parent links |
| `/series/{id}/numpy` | GET | Decode whole series → NumPy (≥ 1.11.0) |
| `/series/{id}/anonymize` | POST | Anonymize series |
| `/series/{id}/modify` | POST | Modify series |
| `/series/{id}/archive`, `/series/{id}/media` | GET, POST | ZIP / DICOMDIR |
| `/series/{id}/shared-tags` | GET | Tags common to all instances |
| `/series/{id}/statistics` | GET | Series statistics |

### Instances

| Path | Methods | Summary |
| --- | --- | --- |
| `/instances` | GET, POST | List instances / **upload** DICOM (POST) |
| `/instances/{id}` | GET, DELETE | Get / delete an instance |
| `/instances/{id}/file` | GET | Download raw DICOM file |
| `/instances/{id}/tags` | GET | Detailed tags (hex keys, VR) |
| `/instances/{id}/simplified-tags` | GET | Human-readable tags |
| `/instances/{id}/content/{path}` | GET | Raw value of a tag / descend sequences |
| `/instances/{id}/header` | GET | DICOM meta-header |
| `/instances/{id}/preview` | GET | 8-bit PNG/JPEG preview (range-stretched) |
| `/instances/{id}/rendered` | GET | Rendered image (windowing applied) |
| `/instances/{id}/image-uint8` | GET | 8-bit PNG (no stretch) |
| `/instances/{id}/image-uint16` | GET | 16-bit PNG |
| `/instances/{id}/image-int16` | GET | Signed 16-bit PNG |
| `/instances/{id}/numpy` | GET | Decode → NumPy (≥ 1.11.0) |
| `/instances/{id}/frames` | GET | List frames |
| `/instances/{id}/frames/{frame}/...` | GET | Per-frame image / numpy / raw |
| `/instances/{id}/pdf` | GET | Embedded PDF |
| `/instances/{id}/anonymize` | POST | Anonymize instance |
| `/instances/{id}/modify` | POST | Modify instance |
| `/instances/{id}/statistics` | GET | Instance statistics |
| `/instances/{id}/patient` / `/study` / `/series` | GET | Parent links |

### Networking — modalities

| Path | Methods | Summary |
| --- | --- | --- |
| `/modalities` | GET | List modalities (`?expand`) |
| `/modalities/{id}` | GET, PUT, DELETE | Get / create-update / remove a modality |
| `/modalities/{id}/configuration` | GET | Modality config |
| `/modalities/{id}/echo` | POST | C-ECHO |
| `/modalities/{id}/store` | POST | C-STORE SCU |
| `/modalities/{id}/query` | POST | C-FIND SCU → creates `/queries/{id}` |
| `/modalities/{id}/move` | POST | C-MOVE SCU |
| `/modalities/{id}/get` | POST | C-GET SCU (≥ 1.12.6) |
| `/modalities/{id}/find-worklist` | POST | C-FIND SCU for worklist |
| `/modalities/{id}/storage-commitment` | POST | Storage-commitment request |

### Networking — peers

| Path | Methods | Summary |
| --- | --- | --- |
| `/peers` | GET | List peers (`?expand`) |
| `/peers/{id}` | GET, PUT, DELETE | Get / create-update / remove a peer |
| `/peers/{id}/store` | POST | Send resources over HTTP(S) |
| `/peers/{id}/system` | GET | Test connectivity (≥ 1.5.9) |

### Query/Retrieve — queries

| Path | Methods | Summary |
| --- | --- | --- |
| `/queries` | GET | List active queries |
| `/queries/{id}` | GET, DELETE | Inspect / drop a query |
| `/queries/{id}/level` | GET | Query level |
| `/queries/{id}/modality` | GET | Queried modality |
| `/queries/{id}/query` | GET | Original query matchers |
| `/queries/{id}/answers` | GET | Answer indices |
| `/queries/{id}/answers/{i}/content` | GET | One answer's details |
| `/queries/{id}/answers/{i}/retrieve` | POST | Retrieve one answer (C-MOVE/C-GET) |
| `/queries/{id}/retrieve` | POST | Retrieve all answers |

### Jobs

| Path | Methods | Summary |
| --- | --- | --- |
| `/jobs` | GET | List jobs (`?expand`) |
| `/jobs/{id}` | GET, DELETE | Get / delete a job |
| `/jobs/{id}/cancel` | POST | Cancel |
| `/jobs/{id}/pause` | POST | Pause |
| `/jobs/{id}/resume` | POST | Resume |
| `/jobs/{id}/resubmit` | POST | Resubmit a failed job |
| `/jobs/{id}/{key}` | GET, DELETE | Get a named job output (e.g. archive) |

---

## Tier 2 — Appendix (long tail)

Rarely needed for typical tooling; included for completeness. Most repeat
identically across the `instances` / `series` / `studies` / `patients` levels.

### Attachments (all four levels)

`/{level}/{id}/attachments` (GET) lists attachment names. Each attachment supports:
`/{level}/{id}/attachments/{name}` (GET, PUT, DELETE) and sub-routes `data`,
`info`, `md5`, `size`, `compressed-data`, `compressed-md5`, `compressed-size`,
`is-compressed`, plus actions `compress`, `uncompress`, `verify-md5` (POST).

### Metadata (all four levels)

`/{level}/{id}/metadata` (GET) lists metadata; `/{level}/{id}/metadata/{name}`
(GET, PUT, DELETE) reads/writes one metadata item.

### Labels (all four levels)

`/{level}/{id}/labels` (GET) lists labels; `/{level}/{id}/labels/{label}`
(GET = test, PUT = add, DELETE = remove). Global list: `/tools/labels`.

### Modules & misc per-resource

`/{level}/{id}/module` (GET) — DICOM module for the level; studies also expose
`/module-patient`. `/{level}/{id}/reconstruct` (POST) rebuilds tags/files.
`/series/{id}/ordered-slices` (GET) is **deprecated**.

### Per-frame & decoding variants (instances/series)

`/instances/{id}/frames/{frame}/{image-uint8|image-uint16|image-int16|preview|rendered|raw|raw.gz|numpy|matlab}`,
plus instance/series-level `/matlab`, `/numpy`.

### Deprecated modality C-FIND helpers

`/modalities/{id}/{find|find-patient|find-study|find-series|find-instance}` — all
**deprecated**; use `/modalities/{id}/query` + the `/queries/...` lifecycle instead.

### Storage commitment

`/storage-commitment/{id}` (GET) — commitment report;
`/storage-commitment/{id}/remove` (POST) — remove after commitment.

### Server configuration & diagnostics (under `/tools`)

`accepted-sop-classes` (GET), `accepted-transfer-syntaxes` (GET, PUT),
`default-encoding` (GET, PUT), `unknown-sop-class-accepted` (GET, PUT),
`dicom-conformance` (GET), `dicom-echo` (POST), `invalidate-tags` (POST),
`reconstruct` (POST), `execute-script` (POST, Lua), `metrics` (GET, PUT),
`metrics-prometheus` (GET), and the log-level family
`log-level`, `log-level-{dicom|generic|http|jobs|lua|plugins|sqlite}` (GET, PUT).
