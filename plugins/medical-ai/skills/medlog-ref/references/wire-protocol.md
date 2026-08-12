# MedLog wire protocol — the five write-once endpoints

Spec 0.0.1. Ground truth: [`assets/openapi-0.0.1.yaml`](../assets/openapi-0.0.1.yaml).

A MedLog record is **never PUT as one document**. It is assembled from up to five
append-only messages, each posted to its own endpoint as it becomes available.

## Endpoints

All are `POST`, all tagged `Events`, all "write-once".

| Endpoint | `operationId` | Body | When |
|----------|---------------|------|------|
| `/event/inference-start` | `postInferenceStart` | `InferenceStartEvent` | Before the model returns — creates `event_id` |
| `/event/internal-artifact` | `postInternalArtifact` | `InternalArtifactEvent` | Per reasoning trace / RAG context / uncertainty estimate |
| `/event/human-output` | `postHumanOutput` | `HumanOutputEvent` | When content is shown to a human |
| `/event/outcome` | `postOutcome` | `OutcomeEvent` | When a downstream outcome can be attributed — often much later |
| `/event/user-feedback` | `postUserFeedback` | `UserFeedbackEvent` | On explicit feedback |

Responses: **201** accepted · **400** invalid payload or missing fields · **401** missing
or invalid credentials · **403** insufficient permissions. Errors return an `Error`
object (`message` required, plus `code`, `details`).

## Auth

API key in a header:

```
X-API-Key: <key>
```

Declared as `ApiKeyAuth` and applied to every endpoint. Never hard-code it — the records
contain PHI, and the collector is a PHI sink.

## Event composition

Every event is `allOf: [BaseEvent, {one payload}]` — so the envelope fields sit at the
**top level**, not inside a `header` object:

```
InferenceStartEvent   = BaseEvent + model_instance + user_identity + target_identity + inputs
InternalArtifactEvent = BaseEvent + artifact
HumanOutputEvent      = BaseEvent + output
OutcomeEvent          = BaseEvent + outcome
UserFeedbackEvent     = BaseEvent + feedback
```

`BaseEvent` requires `event_id`, `timestamp`, `medlog_version`, `system_metadata`.
`InferenceStartEvent` additionally requires all four of its payload objects.

## Assembly and linkage

```
   inference begins
        │
        ├─ POST /event/inference-start          event_id = E1   [run_id = R1]
        │      └─ if this 201s, a record EXISTS even if the model then crashes
        │
        ├─ POST /event/internal-artifact        event_id = E2, parent_event_id = E1
        ├─ POST /event/human-output             event_id = E3, parent_event_id = E1
        │
   ····· hours or days later ·····
        │
        ├─ POST /event/outcome                  event_id = E4, parent_event_id = E1
        └─ POST /event/user-feedback            event_id = E5, parent_event_id = E1
```

- **`event_id`** is unique per *event*, not per record. Each POST mints a new one.
- **`run_id`** stays constant across every event in one inference run — this is what
  groups a multi-stage or agentic workflow.
- **`parent_event_id`** points at the event being expanded. In the paper's AI-AI
  archetype, an orchestrator's event is the parent of the model's.

Writing `inference-start` *before* invoking the model is deliberate: a failed inference
still leaves a record, which is exactly the case post-deployment surveillance cares about.

## Minimal emitter

```python
import uuid
from datetime import datetime, timezone

import requests

BASE = "https://medlog.example.org"          # your collector
S = requests.Session()
S.headers["X-API-Key"] = API_KEY             # from env/secret store, never literal

MEDLOG_VERSION = "0.0.1"


def envelope(run_id=None, parent=None):
    """BaseEvent — the four required fields plus optional linkage."""
    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "medlog_version": MEDLOG_VERSION,
        "system_metadata": {
            "hostname": HOSTNAME,
            "app_name": "cxr-inference",
            "proc_id": str(PID),
        },
        **({"run_id": run_id} if run_id else {}),
        **({"parent_event_id": parent} if parent else {}),
    }


def post(path: str, body: dict) -> str:
    r = S.post(f"{BASE}/event/{path}", json=body, timeout=5)
    r.raise_for_status()                      # 201 expected
    return body["event_id"]


# 1. before the model runs — this is what guarantees a record on failure
start = envelope(run_id=RUN_ID) | {
    "model_instance": {"model_id": "cxr-classifier", "model_version": "2026-05-01"},
    "user_identity": {"caller_type": "service", "caller_id": "ris-worker-3"},
    "target_identity": {"target_type": "patient", "target_id": PSEUDO_MRN},
    "inputs": {"input_uri": f"s3://studies/{study_uid}"},   # pointer, not pixels
}
e1 = post("inference-start", start)

# 2. what the clinician saw
post("human-output", envelope(run_id=RUN_ID, parent=e1) | {
    "output": {"output_type": "text", "output_uri": report_uri,
               "summary": "No acute cardiopulmonary abnormality."},
})

# 3. later, from a separate job
post("outcome", envelope(run_id=RUN_ID, parent=e1) | {
    "outcome": {"outcome_type": "validated", "occurred_at": ts,
                "description": "Radiologist agreed at final read.",
                "evidence_uri": report_uri},
})
```

Emit failures must not take down inference. Queue locally and retry — see the
write-behind pattern in [implementation.md](implementation.md).

## Servers in the spec

The published spec lists a SwaggerHub mock
(`https://virtserver.swaggerhub.com/harvard-647/MedLog/0.0.1`) and
`https://medlog.swagger.io/api/v3`. **Neither is a production collector** — MedLog is
deployed inside an institution. Point `BASE` at your own.
