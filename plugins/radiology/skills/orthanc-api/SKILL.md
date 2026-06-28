---
name: orthanc-api
description: "Reference for driving an Orthanc DICOM server through its REST API. Use this skill whenever a task involves Orthanc — uploading, browsing, searching, downloading, anonymizing, or modifying DICOM resources (patients/studies/series/instances) on a local or remote Orthanc; performing DICOM network operations through Orthanc such as C-ECHO, C-STORE, C-MOVE, C-GET, or Query/Retrieve (C-FIND) against remote modalities/PACS; configuring Orthanc peers or modalities; tracking changes; decoding instances to PNG/NumPy for AI pipelines; or running asynchronous Orthanc jobs. Trigger this even when the user only mentions an Orthanc URL (e.g. localhost:8042), 'the Orthanc REST API', or building a script/tool/pipeline that talks to Orthanc, even if no specific endpoint is named."
metadata:
  version: "2026-06-12"
---

# Orthanc REST API Reference

Orthanc is a lightweight, self-contained DICOM server. Its entire feature set is
exposed over a RESTful HTTP API returning JSON — anything the Orthanc Explorer UI
can do, the REST API can do. This skill is the working reference for that API.

Examples below use Python `requests` as the primary idiom (the common case for
tooling and AI pipelines); `curl` is shown only where it is clearer, mainly for
binary uploads.

## Mental model

Orthanc organizes everything under the DICOM **Patient → Study → Series → Instance**
hierarchy. Each resource has a stable Orthanc ID and links to its parent and children.

```
Patient ──< Study ──< Series ──< Instance
   │           │         │           └─ the actual DICOM file (1 image / object)
   │           │         └─ one acquisition (e.g. one CT sequence)
   │           └─ one imaging exam (one StudyInstanceUID)
   └─ one person

Navigate DOWN via child arrays:   GET /studies/{id}  → {"Series": [...]}
Navigate UP via parent fields:    GET /series/{id}   → {"ParentStudy": "..."}
```

### The #1 source of bugs: two ID systems

```
┌──────────────────────────────────────────────────────────────────────┐
│  ORTHANC ID                  DICOM UID                                 │
│  5d4a3991-8a265cb2-...        1.2.840.113704.1.111...                   │
│  ──────────────────          ─────────────────────                     │
│  SHA-1–derived, stable        the DICOM-standard identity              │
│  Used in REST PATHS:          Used in C-FIND / C-MOVE / C-GET queries  │
│    /studies/{orthanc_id}        {"StudyInstanceUID": "1.2.840..."}     │
│  Returned by upload,          Lives in MainDicomTags                    │
│    /tools/find, /changes                                                │
│                                                                        │
│  Bridge between them:  POST /tools/lookup  (DICOM UID → Orthanc ID)    │
└──────────────────────────────────────────────────────────────────────┘
```

If a path 404s, the usual cause is feeding a DICOM UID where an Orthanc ID is
expected (or vice versa). Use `/tools/lookup` to convert.

### Two more recurring gotchas

```
LOCAL  vs  REMOTE      POST /tools/find          → searches Orthanc's OWN database
                       POST /modalities/{id}/query → C-FIND against a REMOTE modality/PACS

SYNC   vs  ASYNC       Long operations (store, move, get, archive) can run as JOBS.
                       Send "Synchronous": false → get a job ID → poll /jobs/{id}.
                       See references/jobs-and-changes.md.
```

## Connection basics

Default endpoint is `http://localhost:8042`. Auth is HTTP Basic when enabled.
Parameterize both — never hard-code credentials.

```python
import requests

BASE = "http://localhost:8042"
AUTH = ("orthanc", "orthanc")   # or None if AuthenticationEnabled=false
S = requests.Session()
S.auth = AUTH

# Always confirm the server + version BEFORE using version-gated features
sys = S.get(f"{BASE}/system").json()
print(sys["Version"], sys["ApiVersion"])
```

Many features are version-gated (e.g. `numpy` output ≥ 1.11.0, C-GET ≥ 1.12.6,
`OrderBy`/`ExtendedFind` ≥ 1.12.5, `RequestedTags` ≥ 1.11.0, extended `/changes`
≥ 1.12.5). When a workflow notes a minimum version, check `/system` first rather
than calling an endpoint that may not exist on the target install.

## Task → where to look

| If the task is...                                              | Read this reference            |
| -------------------------------------------------------------- | ------------------------------ |
| Look up the exact path / method / summary for any endpoint     | `references/endpoints.md`      |
| Upload DICOM; browse the hierarchy; read DICOM tags            | `references/data-access.md`    |
| Download a file/preview/PNG/**NumPy array**/ZIP/PDF/video      | `references/data-access.md`    |
| Search the LOCAL database (`/tools/find`, `/tools/lookup`)     | `references/data-access.md`    |
| Anonymize, modify, or delete resources (incl. bulk)            | `references/data-access.md`    |
| Configure modalities/peers; C-ECHO/STORE/MOVE/GET              | `references/networking.md`     |
| Query/Retrieve (C-FIND → answers → C-MOVE/C-GET) a remote PACS | `references/networking.md`     |
| Run async jobs, poll status; watch `/changes`; auto-route      | `references/jobs-and-changes.md` |

## Highest-frequency calls (inline quick start)

```python
# 1. Upload a DICOM file (binary body). curl is clearer for raw binary:
#    curl -X POST -H "Expect:" http://localhost:8042/instances --data-binary @CT.dcm
with open("CT.dcm", "rb") as f:
    r = S.post(f"{BASE}/instances", data=f.read())
ids = r.json()   # {"ID","ParentPatient","ParentSeries","ParentStudy","Status"}

# 2. List all resources at a level (returns an array of Orthanc IDs)
studies = S.get(f"{BASE}/studies").json()

# 3. Get one resource (MainDicomTags + parent/child links)
study = S.get(f"{BASE}/studies/{study_id}").json()

# 4. Read human-readable DICOM tags of an instance
tags = S.get(f"{BASE}/instances/{instance_id}/simplified-tags").json()

# 5. Download the raw DICOM file
dcm = S.get(f"{BASE}/instances/{instance_id}/file").content   # write to .dcm

# 6. Find studies in the LOCAL database by DICOM tag
hits = S.post(f"{BASE}/tools/find",
              json={"Level": "Study",
                    "Query": {"PatientName": "DOE*"},
                    "Expand": True}).json()
```

## Conventions used in the references

- `{id}` always means an **Orthanc ID** unless the path says otherwise.
- Resource-listing endpoints return an array of IDs; add `?expand` (or POST
  `"Expand": true` for `/tools/find`) to get full objects instead.
- Errors come back as JSON with `HttpStatus`, `Message`, and often `OrthancError`.
- The canonical, always-current OpenAPI/Swagger spec is at
  <https://orthanc.uclouvain.be/api/>. Use it to confirm parameters for any
  endpoint not detailed here.
