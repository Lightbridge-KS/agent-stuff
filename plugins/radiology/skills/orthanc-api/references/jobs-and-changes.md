# Jobs & Changes — Async Operations and Events

Two cross-cutting mechanisms referenced throughout the other guides: the **job**
system (for long operations run asynchronously) and the **changes log** (for
reacting to new data). Setup (`BASE`, `AUTH`, `S`) is from `SKILL.md`.

## Contents

1. [The async job pattern](#1-the-async-job-pattern)
2. [Monitoring & controlling jobs](#2-monitoring--controlling-jobs)
3. [The changes log](#3-the-changes-log)
4. [Auto-routing pattern](#4-auto-routing-pattern)
5. [Exports log](#5-exports-log)

---

## 1. The async job pattern

Operations that can take a while — C-STORE, C-MOVE, C-GET, retrieve, archive,
anonymize, modify — accept `"Synchronous": false`. Instead of blocking until the
work finishes, Orthanc enqueues a **job** and immediately returns its ID. You then
poll `/jobs/{id}` until it reaches a terminal state.

```
POST .../store {"Synchronous": false, ...}
        │
        ▼
   {"ID": "11541b16-...", "Path": "/jobs/11541b16-..."}
        │
        ▼  poll
   GET /jobs/{id} → {"State": "Pending"|"Running"|"Success"|"Failure"|"Paused", ...}
```

```python
import time

def run_job(resp, interval=1.0, timeout=600):
    """Block on an async Orthanc job until terminal; return the final job object."""
    job_id = resp.json()["ID"]
    deadline = time.monotonic() + timeout
    while True:
        job = S.get(f"{BASE}/jobs/{job_id}").json()
        state = job["State"]
        if state in ("Success", "Failure"):
            return job
        if time.monotonic() > deadline:
            raise TimeoutError(f"job {job_id} still {state} after {timeout}s")
        time.sleep(interval)

resp = S.post(f"{BASE}/modalities/sample/store",
              json={"Resources": [study_id], "Synchronous": False})
job = run_job(resp)
if job["State"] == "Failure":
    raise RuntimeError(job.get("ErrorDescription", "job failed"))
```

A job object carries `State`, `Progress` (0–100), `Type`, `Content` (operation
detail — e.g. DIMSE results, received instance IDs), and timing fields.

## 2. Monitoring & controlling jobs

```python
S.get(f"{BASE}/jobs").json()                       # all jobs
S.get(f"{BASE}/jobs", params={"expand": ""}).json()# with details
S.get(f"{BASE}/jobs/{job_id}").json()              # one job
S.get(f"{BASE}/jobs/{job_id}/{key}").content       # a named job output (e.g. archive)

S.post(f"{BASE}/jobs/{job_id}/cancel")
S.post(f"{BASE}/jobs/{job_id}/pause")
S.post(f"{BASE}/jobs/{job_id}/resume")
S.post(f"{BASE}/jobs/{job_id}/resubmit")           # re-run a failed job
```

## 3. The changes log

Every event (new instance/series/study/patient, stable resource, deletion, etc.) is
appended to a sequential log. This is the supported way for external scripts to
**react to new data** — the call is non-blocking, so you implement the polling loop.

```python
batch = S.get(f"{BASE}/changes", params={"limit": 100}).json()
# {
#   "Changes": [{"ChangeType":"NewInstance","ResourceType":"Instance",
#                "ID":"...","Path":"/instances/...","Date":"20130507T143902",
#                "Seq":921}, ...],
#   "Done": true,    # false ⇒ more events available beyond this batch
#   "Last": 924      # highest Seq returned; use as the next `since`
# }
```

Drive a polling loop with `since` (resume point) + `limit` (batch size):

```python
def poll_changes(since=0, limit=100):
    """Yield change events forever, resuming from the last seen Seq."""
    while True:
        page = S.get(f"{BASE}/changes",
                     params={"since": since, "limit": limit}).json()
        for change in page["Changes"]:
            yield change
            since = change["Seq"]
        if page["Done"]:
            time.sleep(1.0)        # caught up; wait before re-polling
        # else: loop straight on to drain the backlog
```

A single received instance produces four changes (NewInstance, NewSeries,
NewStudy, NewPatient). Prefer the **Stable** events (`StableStudy`, etc.) when you
need a resource that is finished receiving rather than mid-transfer.

**Extended changes (≥ 1.12.5; SQLite or PostgreSQL ≥ 7.0):** filter by `type` and
reverse order via `to`:

```python
S.get(f"{BASE}/changes",
      params={"type": "StableStudy;NewPatient", "to": 7584, "limit": 100})
```

Clear the log with `DELETE /changes`.

## 4. Auto-routing pattern

Combine the changes loop with a C-STORE to forward incoming studies automatically.
Trigger on `StableStudy` (not `NewInstance`) so the whole study has arrived first.

```python
for change in poll_changes(since=last_seen_seq):
    if change["ChangeType"] == "StableStudy":
        study_id = change["ID"]
        S.post(f"{BASE}/modalities/destinationPACS/store",
               json={"Resources": [study_id], "Synchronous": False})
        last_seen_seq = change["Seq"]   # persist this to survive restarts
```

Persist the last `Seq` so a restart resumes rather than reprocessing. For pure
forwarding, Lua-based auto-routing inside Orthanc is an alternative that avoids an
external process; the REST/changes loop is preferable when routing needs custom
logic (filtering, anonymization, logging) before sending.

## 5. Exports log

When `LogExportedResources` is enabled (default `false` since 1.4.0), Orthanc records
resources sent to remote modalities — useful for medical traceability.

```python
S.get(f"{BASE}/exports").json()      # the export log
S.delete(f"{BASE}/exports")          # clear it (do this periodically in auto-routing)
```
