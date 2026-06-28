# Full command surface

Every command group in `slicer-cli`. Each entry lists the signature, the
underlying Slicer endpoint (where applicable), and one example.

For deeper rationale, the canonical reference is `docs/Slicer-CLI-UserManual.md`
in this repo (§4 covers the same surface in narrative form).

## Global flags

| Flag | Default | Notes |
|---|---|---|
| `--url URL` | `http://127.0.0.1:2016` | Slicer base URL |
| `--timeout SECONDS` | `30` | HTTP timeout |
| `--json` / `--pretty` | `--pretty` on TTY | `--json` for agent use |
| `--quiet` | off | suppresses non-error chatter (partial) |
| `--version` | — | print CLI version and exit |

Layered config precedence (highest first): flag → env (`SLICER_URL`,
`SLICER_TIMEOUT`, `SLICER_EXEC_ENABLED`) → project `.slicer-cli.toml` →
`~/.config/slicer-cli/config.toml` → built-in defaults. Inspect the merged
result with `slicer-cli config show --json`.

Global flags may appear before or after the verb:
`slicer-cli --json status` and `slicer-cli status --json` are equivalent.

---

## `status` (top-level)

Liveness + version probe.

```bash
slicer-cli --json status
```

Endpoint: `GET /slicer/system/version`.

## `doctor` (top-level)

Capability matrix — runs independent probes (reachable, slicer-api,
dicomweb, power-tool-endpoint, render-slice, render-threed). One failing
probe does not abort the rest.

```bash
slicer-cli --json doctor | jq '.checks[]'
```

## `system`

| Command | Description |
|---|---|
| `system version` | Same data as top-level `status`, scoped under `system`. |
| `system shutdown --confirm` | **Destructive.** `DELETE /slicer/system`. Requires `--confirm`; without it returns `E_DESTRUCTIVE`. |

## `scene`

| Command | Description |
|---|---|
| `scene nodes [--class C] [--name N]` | All MRML nodes as `{id, name, class}`. |
| `scene ids [--class C] [--name N]` | Just ids — terse, ideal for piping. |
| `scene clear --confirm` | **Destructive.** Wipes the entire scene. Without `--confirm` → `E_DESTRUCTIVE`. |
| `scene save <path>` | Save scene to `.mrb` / `.mrml`. Routes through `/slicer/exec` (Slicer has no native save endpoint); requires power-tool enabled. |
| `scene load <path>` | Load a `.mrb` / `.mrml` from a server-readable path. |

## `node`

| Command | Description |
|---|---|
| `node show <id>` | Full property dict for one node. |
| `node delete <id>` | Delete one node. Empty/whitespace `<id>` → `E_EMPTY_SELECTOR`. |
| `node reload <id>` | Re-load node from its underlying file. |

## `volume`

| Command | Description |
|---|---|
| `volume list` | All scalar/labelmap volumes (id, name, class). |
| `volume show <id>` | Property dict for one volume node. |
| `volume import <path> [--name N]` | Load a NRRD/NIfTI/etc. as a new volume node. Path must be readable by **Slicer**. |
| `volume export <id> --out path\|-` | Stream NRRD bytes to disk. `--out` mandatory. `--out -` → stdout (binary), envelope on stderr. |
| `volume delete <id>` | Delete one volume node (same empty-id guard as `node delete`). |

## `sample`

| Command | Description |
|---|---|
| `sample list` | Curated catalogue of verified Slicer samples. Pure offline. |
| `sample load <name>` | Triggers Slicer's `SampleData` module to download/load. Accepts any string. |

## `render`

All four `render` commands write binary content. `--out` is mandatory.

| Command | Description |
|---|---|
| `render slice [--view red\|yellow\|green] [--orientation axial\|sagittal\|coronal] [--offset MM] [--scroll-to 0..1] [--size PX] --out path\|-` | Render one slice viewer to PNG. Default `--view red`. |
| `render threed [--look A\|P\|L\|R\|I\|S] --out path\|-` | Render the first 3D view to PNG from a cardinal axis. Arbitrary cameras need `exec`. |
| `render screenshot --out path\|-` | Grab Slicer's main window as PNG. Requires the GUI to be alive. |
| `render gltf [--widget 0] --out path\|-` | Export a 3D widget as glTF (Slicer 5.11 returns JSON glTF, ~10 KB). |

The client validates every PNG response (magic-bytes + size ≥ 256 bytes +
non-zero IHDR). On failure → `E_BAD_RESPONSE` with a hint that contains
`GALLIUM_DRIVER=llvmpipe` (the fix for headless Linux without GPU).

## `markup`

| Command | Description |
|---|---|
| `markup list [--type fiducial\|segmentation]` | List markup nodes. No `--type` → merged fiducials + segmentations with a `kind` discriminator. |
| `markup fiducial-set --id NODE_ID --index N --r R --a A --s S` | Set position of one fiducial control point (PUT `/slicer/fiducial`). Refuses empty `--id`. |
| `markup line --p1 R,A,S --p2 R,A,S [--name N]` | Create a `vtkMRMLMarkupsLineNode` between two RAS points. Templated `/exec`; audited. |

Lines, angles, curves, planes, and ROIs all share the templated-`/exec`
pattern (Slicer has no native HTTP endpoint for them).

## `dicom`

Slicer's DICOMweb endpoints (`/dicom/*`) read from `slicer.dicomDatabase`
— anything not yet imported into Slicer's local DB is invisible to QIDO
queries. Use `dicom pull` to populate the DB from a DICOMweb peer
(typically Orthanc).

| Command | Description |
|---|---|
| `dicom studies [--patient PID] [--limit N] [--offset N]` | QIDO list studies. Common DICOM tags flattened into Pythonic fields. |
| `dicom series <studyUID>` | QIDO list series for a study. |
| `dicom instances <studyUID> <seriesUID>` | QIDO list instances for a series. |
| `dicom instance <studyUID> <seriesUID> <sopUID> --out path\|-` | WADO-RS retrieve. Writes raw DICOM Part-10 bytes. `--out` required. |
| `dicom meta <studyUID> [<seriesUID> [<sopUID>]]` | DICOM JSON Model metadata at study, series, or instance level. |
| `dicom pull --orthanc <url> --study <UID> [--store dicom-web] [--token T]` | Import a study from a DICOMweb peer into Slicer's DB. Routes through `/slicer/exec`. |

Full Orthanc workflow → `dicomweb.md`.

## `exec` (gated + audited)

| Command | Description |
|---|---|
| `exec --code 'python source'` | POST source to `/slicer/exec`. The source MUST set `__execResult` to a JSON-serializable value. |
| `exec --file path/to/script.py` | Same as `--code` but reads source from a file. |
| `exec ... --no-audit-log` | Skip writing the audit-log line (emits stderr warning). |
| `exec ... --i-understand-the-risk` | Required when `config.exec.enabled = false`. |

Audit log lives at `~/.local/state/slicer-cli/exec.log`. See `safety.md`.

## `gui`

| Command | Description |
|---|---|
| `gui layout LAYOUT [--contents full\|viewers]` | PUT `/slicer/gui` to switch viewer layout. `LAYOUT` is pass-through (Slicer 5.x: `fourup`, `oneup3d`, `conventionalwidescreen`, `compareview`, …). `--contents viewers` hides GUI chrome. |

## `api`

| Command | Description |
|---|---|
| `api routes [--method M] [--destructive] [--phase "Phase N"]` | Offline route inventory. Filter by HTTP method, destructiveness, or phase. |
| `api raw <method> <path> [--query K=V ...] [--body @file] [--out path] [--confirm]` | Issue an arbitrary HTTP call. JSON responses parsed into envelope; non-JSON requires `--out`. Destructive `(method, path)` pairs require `--confirm`. |

## `config`

| Command | Description |
|---|---|
| `config show [--json]` | Print the merged config. |
| `config get <key>` | Print one key (e.g., `server.url`). |
| `config path` | Print which TOML files were loaded. |

---

## Output mode short reference

| Mode | When | What stdout looks like |
|---|---|---|
| `--json` | always for agents | one-line `{"ok": true, ...}` envelope |
| `--pretty` | TTY humans | rich tables / panels |
| `--quiet` | scripted health checks | empty stdout on success |

For binary commands using `--out -`, the success envelope routes to
**stderr** in `--json` mode so stdout stays pure binary.
