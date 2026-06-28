---
name: slicer-cli
description: Drive 3D Slicer (medical imaging app) over HTTP via the slicer-cli tool. Use when the user mentions Slicer, MRML, DICOM viewing/loading from a Slicer scene, or asks to render a slice/3D view from a volume they have loaded in Slicer.
license: MIT
compatibility: Requires the `slicer-cli` Python tool installed and a running 3D Slicer 5.x with the WebServer module started on port 2016.
metadata:
  version: "2026-06-12"
---

# slicer-cli — drive 3D Slicer over HTTP

`slicer-cli` is an agent-first wrapper around 3D Slicer's in-process HTTP
server (default `http://127.0.0.1:2016`). This skill teaches you when to
invoke it and how to do so safely.

> **Tool:** this skill drives the `slicer-cli` tool at
> <https://github.com/Lightbridge-KS/slicer-cli>. Install it from there.

## When to use

Invoke this skill when the user:

- Asks to interact with a running 3D Slicer instance, the MRML scene, or any Slicer node.
- Wants to load, list, inspect, export, or delete volumes inside Slicer.
- Asks to render a slice viewer or 3D view from a volume currently loaded in Slicer.
- Wants to query Slicer's DICOM database via DICOMweb (QIDO/WADO) or pull a study from Orthanc into Slicer.
- Asks to switch Slicer's GUI layout or grab a screenshot of the Slicer window.

Do NOT invoke this skill for:

- Parsing raw DICOM files outside of Slicer (use `pydicom` or similar).
- Writing image-segmentation algorithms (Slicer modules do this; the CLI does not).
- Launching the Slicer GUI itself (the user starts Slicer manually).
- DICOM DIMSE protocol work (C-STORE, C-FIND, C-MOVE) — that is a separate domain.

## First contact (do this on every fresh task)

```bash
slicer-cli --json status
```

- On `ok: true` → proceed.
- On `ok: false` with `code: E_NOT_RUNNING` → **stop**. Tell the user Slicer
  is not reachable. Do not fabricate Slicer state.

Optionally cache `slicer-cli --json doctor` once per session to know which
capability probes (`render`, `dicomweb`, `power-tool-endpoint`, …) are green.
Do not re-run `status` / `doctor` between every command.

## Output contract — always pass `--json`

Every invocation should pass `--json`. Output is one JSON object per call.

**Success envelope:**

```json
{"ok": true, "<key>": "...", "<key>": "..."}
```

**Failure envelope:**

```json
{
  "ok": false,
  "error": {
    "code": "E_HTTP_5XX",
    "message": "...",
    "hint": "...",
    "endpoint": "/slicer/...",
    "http_status": 500
  }
}
```

**Branch on `error.code`, never on `error.message`.** Codes are stable
public API; messages may be reworded between releases.

Exit code summary (full table → `references/errors.md`):

| Exit | Meaning |
|---|---|
| 0 | success |
| 1 | bad CLI input (`E_BAD_INPUT`) |
| 2 | Slicer-side HTTP error (`E_HTTP_4XX/5XX`, `E_BAD_RESPONSE`) |
| 3 | network (`E_NOT_RUNNING`, `E_NETWORK`, `E_TIMEOUT`) |
| 4 | config (`E_CONFIG`) |
| 5 | exec disabled (`E_EXEC_DISABLED`) |
| 6 | destructive guard fired (`E_DESTRUCTIVE`, `E_EMPTY_SELECTOR`) |
| 7 | not yet implemented (`E_NOT_IMPLEMENTED`) |

## Safety rules (non-negotiable)

1. **Never run these without explicit user instruction:**
   - `slicer-cli scene clear --confirm` (wipes the entire MRML scene).
   - `slicer-cli system shutdown --confirm` (kills the Slicer process).
   - `slicer-cli exec --code '…'` / `--file …` (arbitrary Python in Slicer's process).

2. **Hard-stop error codes — surface, do NOT retry, do NOT "fix" by adding flags:**
   - `E_DESTRUCTIVE` → the user did not authorize the destructive action. Surface it; ask the user.
   - `E_EMPTY_SELECTOR` → an empty `<id>` was passed. Don't substitute `--all`. Ask.
   - `E_NOT_IMPLEMENTED` → the feature lives in a later phase. The `hint` says which. Don't emulate via `api raw` or `exec` unless the user explicitly asks.
   - `E_EXEC_DISABLED` → don't auto-pass `--i-understand-the-risk`. Ask.

3. **Binary commands require `--out`:** `volume export`, `dicom instance`,
   `render slice|threed|screenshot|gltf`, and `api raw …` writing non-JSON.
   Pass `--out -` only when piping into another process. In `--out -` mode
   the success envelope routes to **stderr**; stdout is pure binary.

4. **Read `references/safety.md` before touching anything destructive or
   before invoking `exec`.**

## Common commands (the 80% surface)

| Command | One-line example |
|---|---|
| `status` | `slicer-cli --json status` |
| `doctor` | `slicer-cli --json doctor` |
| `scene nodes [--class C] [--name N]` | `slicer-cli --json scene nodes --class vtkMRMLScalarVolumeNode` |
| `scene ids` | `slicer-cli --json scene ids \| jq -r '.ids[]'` |
| `node show <id>` | `slicer-cli --json node show vtkMRMLScalarVolumeNode1` |
| `node delete <id>` | `slicer-cli --json node delete vtkMRMLScalarVolumeNode2` |
| `volume list` | `slicer-cli --json volume list` |
| `volume show <id>` | `slicer-cli --json volume show vtkMRMLScalarVolumeNode1` |
| `volume export <id> --out PATH` | `slicer-cli --json volume export vtkMRMLScalarVolumeNode1 --out /tmp/mr.nrrd` |
| `volume import <path> [--name N]` | `slicer-cli --json volume import /data/img.nrrd --name MyImg` |
| `render slice [--orientation …] [--offset MM] --out PATH` | `slicer-cli --json render slice --orientation axial --offset 12 --out /tmp/ax.png` |
| `render threed [--look A\|P\|L\|R\|I\|S] --out PATH` | `slicer-cli --json render threed --look A --out /tmp/3d.png` |
| `dicom studies [--patient PID]` | `slicer-cli --json dicom studies --patient 12345` |
| `dicom series <studyUID>` | `slicer-cli --json dicom series 1.2.840…` |
| `dicom instance <study> <series> <sop> --out PATH` | `slicer-cli --json dicom instance … --out /tmp/cxr.dcm` |
| `sample load <name>` | `slicer-cli --json sample load MRHead` |
| `api routes [--method M] [--destructive]` | offline route inventory |
| `api raw <method> <path> --out PATH` | escape hatch for unwrapped endpoints |

For everything else (`gui layout`, `markup *`, `exec`, `config get/show`,
`system shutdown`, full flag lists) → `references/commands.md`.

## Worked examples

### Example 1 — Render an axial slice from MRHead at offset 12 mm

```bash
# 1. Probe.
slicer-cli --json status

# 2. Find the MRHead volume id.
MR_ID=$(slicer-cli --json volume list \
  | jq -r '.volumes[] | select(.name == "MRHead") | .id')

# 3. Render.
slicer-cli --json render slice \
  --orientation axial --offset 12 --out /tmp/ax.png
```

`render slice` uses a named view (`--view red`/`yellow`/`green`, default
`red`); `--orientation` and `--offset` set the slice plane within that view.

### Example 2 — Export a volume to NRRD on disk

```bash
slicer-cli --json volume export vtkMRMLScalarVolumeNode1 \
  --out /tmp/mr.nrrd
file /tmp/mr.nrrd        # → "NRRD0004 ..."
```

`--out` is mandatory. Use `--out -` only when piping into another process;
in that mode the success envelope (`{"ok": true, "bytes": N, …}`) routes
to stderr.

### Example 3 — DICOMweb QIDO (list studies for a patient)

```bash
slicer-cli --json dicom studies --patient 12345 \
  | jq '.studies[] | {patient_name, study_date, study_description}'
```

If the result is `[]`, Slicer's DICOM database has no matching studies —
`dicom pull` populates it from a remote DICOMweb peer. See
`references/dicomweb.md`.

### Example 4 — Cleanup pattern after `sample load`

When loading throwaway sample data and you need to clean up afterwards,
capture node ids before AND after, then delete by id:

```bash
BEFORE=$(slicer-cli --json scene ids | jq -r '.ids[]' | sort)
slicer-cli --json sample load CTAAbdomenPanoramix
AFTER=$(slicer-cli --json scene ids | jq -r '.ids[]' | sort)

for id in $(comm -13 <(echo "$BEFORE") <(echo "$AFTER")); do
  slicer-cli --json node delete "$id"
done
```

Don't try to find new nodes by name — sample loads create multiple nodes
with version-dependent names. Diffing ids is robust.

### Example 5 — Capability check before render-heavy work

```bash
slicer-cli --json doctor | jq '.checks[] | select(.ok == false)'
```

- empty output → all probes green; proceed.
- `name: "render"` failing → render commands will fail with
  `E_BAD_RESPONSE` and a hint mentioning `GALLIUM_DRIVER=llvmpipe`.
- `name: "dicomweb"` failing → `/dicom/*` endpoints unavailable.
- `name: "power-tool-endpoint"` failing → `scene save`, `dicom pull`,
  `markup line`, and `exec` will 5xx.

If a probe is red, surface that to the user before falling back.

## Discovery — learn the surface, don't guess

```bash
slicer-cli --json api routes                  # offline route inventory
slicer-cli --json api routes --destructive    # routes that need --confirm
slicer-cli --json api routes \
  | jq '.routes[] | select(.note != null)'    # routes with known caveats
slicer-cli --json doctor                      # live capability probe
```

`api routes` is offline — it works without Slicer running. Use it to pick
the right command/endpoint for a task. The `note` field flags Slicer-side
bugs and CLI workarounds (e.g., `accessDICOMwebStudy` is bypassed via
`/exec`).

## When to load a reference file

| Situation | File |
|---|---|
| Need a less-common command (`gui layout`, `markup line`, `config`, all flags) | `references/commands.md` |
| Hit an unfamiliar `error.code` or want the full code ↔ exit map | `references/errors.md` |
| About to do something destructive, or the user asked to use `exec` | `references/safety.md` |
| Working with DICOMweb / Orthanc / `dicom pull` | `references/dicomweb.md` |
| A command failed unexpectedly and the error doesn't tell you why | `references/troubleshooting.md` |