# DICOM Networking — Remote Modalities & Peers

Talking to the outside world: configuring remote DICOM nodes, testing
connectivity, and running the DIMSE operations (C-ECHO, C-STORE, C-MOVE, C-GET,
C-FIND) plus Orthanc-to-Orthanc HTTP peering. Setup (`BASE`, `AUTH`, `S`) is from
`SKILL.md`.

> **Local vs remote:** everything here reaches a *remote* node. To search Orthanc's
> own database use `POST /tools/find` (`references/data-access.md`), not C-FIND.

## Contents

1. [Configuring modalities](#1-configuring-modalities)
2. [C-ECHO (connectivity test)](#2-c-echo-connectivity-test)
3. [C-STORE (send to a modality)](#3-c-store-send-to-a-modality)
4. [C-MOVE](#4-c-move)
5. [C-GET](#5-c-get)
6. [DIMSE error status](#6-dimse-error-status)
7. [Query/Retrieve lifecycle (C-FIND → retrieve)](#7-queryretrieve-lifecycle-c-find--retrieve)
8. [Orthanc peers (HTTP/HTTPS)](#8-orthanc-peers-httphttps)

---

## 1. Configuring modalities

A modality is a remote DICOM node identified by AET + host + port. Declare them in
the configuration file under `DicomModalities`, or manage them at runtime via REST.

```jsonc
// configuration file
"DicomModalities": {
  "sample":  ["ORTHANCA", "127.0.0.1", 2000],     // short: [AET, Host, Port]
  "sample2": {                                     // long form
    "AET": "ORTHANCB", "Host": "127.0.0.1", "Port": 2001,
    "AllowEcho": true, "AllowFind": true,
    "AllowMove": true, "AllowStore": true,
    "RetrieveMethod": "C-MOVE"                     // or "C-GET" (per-modality override)
  }
}
```

Runtime management (changes live in memory unless `DicomModalitiesInDatabase:true`):

```python
S.get(f"{BASE}/modalities", params={"expand": ""}).json()    # list, with details
S.put(f"{BASE}/modalities/sample",
      json={"AET": "ORTHANCC", "Host": "127.0.0.1", "Port": 2002})
S.delete(f"{BASE}/modalities/sample")
S.get(f"{BASE}/modalities/sample/configuration").json()
```

## 2. C-ECHO (connectivity test)

Verify the DICOM association before anything else. A valid JSON body is required
(≥ 1.7.0); `Timeout` is optional (falls back to `DicomScuTimeout`; `0` = no timeout).

```python
r = S.post(f"{BASE}/modalities/sample/echo", json={"Timeout": 10})
r.raise_for_status()   # 200 = the remote answered
```

## 3. C-STORE (send to a modality)

Push resources from Orthanc to a remote modality. The body may be a single Orthanc
ID, or a JSON array (Bulk Store — one association for many resources). IDs may be at
any level (patient/study/series/instance).

```python
# Simple: one resource
S.post(f"{BASE}/modalities/sample/store", data=study_id)

# Bulk: array of IDs over a single DICOM association (lower overhead)
S.post(f"{BASE}/modalities/sample/store", json=[id1, id2, id3])

# Full options, asynchronous (returns a job ID to poll)
job = S.post(f"{BASE}/modalities/sample/store", json={
    "Resources": [study_id],
    "Synchronous": False,
    "LocalAet": "ORTHANC",
    "MoveOriginatorAet": "ORTHANC",   # set when relaying a C-MOVE
    "MoveOriginatorID": 1234,
    "Timeout": 10,
    "StorageCommitment": False,
}).json()
```

To send many isolated instances efficiently without bulk arrays, set
`DicomAssociationCloseDelay` so the association stays open between calls (useful for
Lua auto-routing). See `references/jobs-and-changes.md` for job polling.

## 4. C-MOVE

Ask a remote node to send matching resources to a target AET. If `TargetAet` is
omitted, the destination is Orthanc itself. Match by DICOM UID(s) at the chosen
`Level`.

```python
S.post(f"{BASE}/modalities/sample/move", json={
    "Level": "Study",
    "Resources": [{"StudyInstanceUID": "1.2.840.113543.6.6.4.7.640675..."}],
    "TargetAet": "ORTHANCB",
    "Timeout": 60,
})
```

## 5. C-GET

**≥ Orthanc 1.12.6.** Retrieve matching resources directly into this Orthanc over
the same association (no separate inbound C-STORE, so it traverses NAT/firewalls
more easily than C-MOVE).

```python
S.post(f"{BASE}/modalities/sample/get", json={
    "Level": "Study",
    "Resources": [{"StudyInstanceUID": "1.2.840.113543.6.6.4.7.640675..."}],
    "Timeout": 60,
})
```

When the study contains uncommon SOP classes, Orthanc only proposes ~120 common
ones by default; declare the others so they are negotiated (subject to
`AcceptedSopClasses`/`RejectedSopClasses`):

```python
"Resources": [{
    "StudyInstanceUID": "1.2.840...",
    "SOPClassesInStudy": "1.2.840.10008.5.1.4.34.10\\1.2.840.10008.5.1.4.34.7",
}]
```

## 6. DIMSE error status

**≥ Orthanc 1.12.10.** C-MOVE / C-GET / C-STORE responses expose the per-resource
DIMSE status and (for retrieves) the IDs actually received.

- **Permissive** (`"Permissive": true`): the call succeeds (HTTP 200) and reports
  each resource's `DimseErrorStatus` and `ReceivedInstancesIds` in `Details[]`.
  `DimseErrorStatus: 0` = success; non-zero (e.g. `49152` / `0xC000`) = that
  resource failed.
- **Non-permissive** (default): the first failure makes the whole call return
  HTTP 500 with a `RetrieveJob`/`Dimse` error payload carrying the same `Content`
  detail.

```python
r = S.post(f"{BASE}/modalities/sample/move", json={
    "Permissive": True, "Level": "Study", "TargetAet": "ORTHANC",
    "Resources": [{"StudyInstanceUID": "1.2.3"}, {"StudyInstanceUID": "3.4.5"}],
})
for d in r.json()["Details"]:
    ok = d["DimseErrorStatus"] == 0
    print(d["Query"]["0020,000d"], "OK" if ok else "FAILED", d["ReceivedInstancesIds"])
```

For async operations the same detail appears under the job's `Content.Details`.

## 7. Query/Retrieve lifecycle (C-FIND → retrieve)

Q/R is a **stateful, multi-step** flow. A query creates a server-side resource under
`/queries/{id}`; you inspect its answers, then retrieve some or all of them.

```
 ┌── POST /modalities/{m}/query ─────────────► returns {"ID": query_id, "Path": ...}
 │        body: {"Level","Query":{...}}
 │
 ├── GET /queries/{query_id}/answers ────────► ["0","1","2",...]  (indices)
 │   GET /queries/{query_id}/answers/{i}/content   (details of one answer)
 │   GET /queries/{query_id}/level | /modality | /query   (inspect the query)
 │
 └── POST /queries/{query_id}/retrieve ──────► fetch ALL answers
     POST /queries/{query_id}/answers/{i}/retrieve   fetch ONE answer
```

Step 1 — fire the C-FIND. Same value syntax as `/tools/find` (wildcards, date
ranges, backslash lists). Empty string = "return this tag" (a universal matcher).

```python
q = S.post(f"{BASE}/modalities/sample/query", json={
    "Level": "Study",
    "Query": {"PatientID": "", "PatientName": "", "StudyDescription": "*Chest*"},
    # "Normalize": False,   # bypass normalization to query non-standard tags
}).json()
query_id = q["ID"]
```

Step 2 — review answers:

```python
answers = S.get(f"{BASE}/queries/{query_id}/answers").json()        # ["0","1",...]
first = S.get(f"{BASE}/queries/{query_id}/answers/0/content").json()
```

If an answer is missing a tag you need, add that tag (empty value) to the original
`Query` and re-run, e.g. `"ModalitiesInStudy": ""`.

Step 3 — retrieve. The method is **C-MOVE or C-GET**, decided by
`DicomDefaultRetrieveMethod` (default `C-MOVE`), the modality's `RetrieveMethod`, or
an explicit `RetrieveMethod` in the payload.

```python
# C-MOVE: the body is the destination AET
S.post(f"{BASE}/queries/{query_id}/retrieve", data="ORTHANC")
S.post(f"{BASE}/queries/{query_id}/answers/0/retrieve", data="ORTHANC")  # one answer

# C-GET: empty body (this Orthanc is the destination)
S.post(f"{BASE}/queries/{query_id}/retrieve", data="")

# Async (recommended for large studies) → returns a job ID to poll
job = S.post(f"{BASE}/queries/{query_id}/retrieve", json={
    "TargetAet": "ORTHANC",          # omit for C-GET
    "RetrieveMethod": "C-MOVE",      # or "C-GET"
    "Synchronous": False,
}).json()
```

## 8. Orthanc peers (HTTP/HTTPS)

Peers send DICOM between Orthanc servers over HTTP(S) instead of the DICOM
protocol — handy across firewalls. Declare under `OrthancPeers`, or manage at
runtime (persist with `OrthancPeersInDatabase:true`).

```jsonc
"OrthancPeers": {
  "sample":  ["http://localhost:8043"],            // short
  "sample2": {                                      // long
    "Url": "http://localhost:8044",
    "Username": "alice", "Password": "alicePassword",
    "HttpHeaders": {"Token": "Hello world"},
    "CertificateFile": "client.crt",                // client-cert auth (optional)
    "CertificateKeyFile": "client.key"
  }
}
```

```python
S.get(f"{BASE}/peers", params={"expand": ""}).json()
S.put(f"{BASE}/peers/sample", json={"Url": "http://127.0.0.1:8043"})
S.delete(f"{BASE}/peers/sample")

# Test connectivity without sending data (≥ 1.5.9): fetches the peer's /system
S.get(f"{BASE}/peers/sample/system").json()

# Send resources (single ID or array; whole patients/studies/series allowed)
S.post(f"{BASE}/peers/sample/store", data=study_id)
S.post(f"{BASE}/peers/sample/store", json=[id1, id2, id3])
```

**Important:** peer transfers move DICOM only — neither **metadata** nor
**attachments** are transferred, since those are local to each Orthanc server.
For internet transfers use HTTPS (terminate TLS in front of Orthanc; supply
`HttpsCACertificates` and, optionally, client certificates).
