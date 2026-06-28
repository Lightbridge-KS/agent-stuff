# Troubleshooting

Symptom → cause → fix table for the most common failures. When the
`error.code` and `hint` aren't enough, walk this table.

| Symptom | Likely cause | Fix |
|---|---|---|
| `E_NOT_RUNNING` on `status` | WebServer module not started in Slicer | Start it from Slicer's *Web Server* module (search "Web Server" in the *Welcome* module → click **Start server**). |
| `E_HTTP_5XX` on `scene save` / `dicom pull` / `markup line` / `exec`, with body containing `unknown command "b'/exec'"` | `/slicer/exec` is disabled in this Slicer build | Enable `/exec` in Slicer's WebServer settings, or skip these commands (they all require the power-tool endpoint). |
| `E_HTTP_5XX` on `volume export` with unknown id | The volume isn't loaded in Slicer | Run `volume list` first; verify the id exists. |
| `volume export` writes a 0-byte file | Slicer responded but the volume node was empty | Inspect with `volume show <id>` — check `Spacing`, `Origin`, `Dimensions` for sanity. |
| `api raw` blocks with `E_DESTRUCTIVE` even though method is `GET` | Path matches a destructive override in `client.routes.DESTRUCTIVE_RAW` | Run `api routes --destructive` to see the list. If you genuinely want to call it, pass `--confirm`. |
| `E_BAD_RESPONSE` on `render slice` / `render threed` with hint mentioning `GALLIUM_DRIVER=llvmpipe` | Headless Linux without GPU; no software-OpenGL fallback | User must `export GALLIUM_DRIVER=llvmpipe` **before** launching Slicer. |
| `dicom studies` returns `[]` even after `dicom pull` succeeded | Slicer's DICOM DB is per-instance, not Orthanc-backed; filter mismatch | The pulled study lives inside Slicer's DB; re-run without `--patient` to sanity-check. `dicom pull` for an already-imported study is idempotent. |
| `dicom pull` 404 on `dicom-web/` paths against Orthanc | Orthanc's DICOMweb plugin isn't loaded | Install OrthancDicomWeb (`brew install orthanc-dicomweb` on macOS), add `"OrthancDicomWeb"` to `Plugins` in `orthanc.json`, restart Orthanc. |
| `render screenshot` returns `E_BAD_RESPONSE` | Slicer GUI not alive (running in `--no-main-window` mode) | `render screenshot` requires the GUI; use `render slice` or `render threed` instead. |
| `E_TIMEOUT` on `volume export` / `dicom instance` | Large file; default 30 s timeout exceeded | Pass `--timeout 120` (or larger) globally. |
| `E_BAD_INPUT` on `markup line` saying RAS coords malformed | `--p1` / `--p2` not in `R,A,S` format | Use comma-separated decimals: `--p1 0,0,0 --p2 50,0,0`. |

## Agent diagnostic flow

When in doubt, walk this:

```
1. slicer-cli --json status
   └── E_NOT_RUNNING  → tell user; stop.
   └── ok             → continue.

2. slicer-cli --json doctor
   └── any check.ok = false → that explains most "should-work-but-doesnt"
                              symptoms (render, dicomweb, power-tool).
   └── all green            → continue.

3. slicer-cli --json api routes \
     | jq '.routes[] | select(.note != null)'
   └── any note matching the endpoint that's failing → known caveat;
       the note tells you what to do (often: bypass via /exec).

4. If still puzzled: re-read the failure envelope's `hint` field
   verbatim and act on it. Do not invent fixes.
```

## When the failure isn't on the CLI side

Some classes of failure live in Slicer itself, not in the CLI:

- Volume rendering crashes inside Slicer → check Slicer's own *Python
  Console* output; the CLI can't see those.
- DICOM database corruption (`SQLITE_CORRUPT` in Slicer's logs) → user
  needs to rebuild Slicer's DB via *DICOM* module → *Database* settings.
- Slicer's GUI froze → only the user can fix this; `system shutdown`
  will not help if the event loop is stuck.

In these cases, surface what you observed and ask the user to look at
Slicer directly. Don't try to "auto-recover" with `system shutdown`
followed by `slicer-cli sample load …` — restarting Slicer drops the
user's loaded data.

## Pointer

`docs/Slicer-CLI-UserManual.md` §9 has the same table in narrative form
and a couple of additional dev-mode entries (e.g., `pytest` + `respx`
quirks).
