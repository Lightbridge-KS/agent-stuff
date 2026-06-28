# DICOMweb workflow (Orthanc → Slicer → QIDO/WADO)

Slicer's DICOMweb endpoints (`/dicom/*`) read from `slicer.dicomDatabase`
— anything not yet imported into Slicer's local DB is invisible to QIDO
queries. The pattern is:

1. Use `dicom pull` to import a study from a remote DICOMweb peer
   (typically Orthanc) into Slicer's DB.
2. Then use `dicom studies` / `dicom series` / `dicom instances` (QIDO)
   to enumerate, and `dicom instance --out` (WADO-RS) to retrieve the
   raw Part-10 bytes.

## Prerequisites

- A running DICOMweb peer (Orthanc by default, on `http://localhost:8042`).
- The peer's DICOMweb plugin loaded. For Orthanc on macOS:
  `brew install orthanc-dicomweb`, then add `"OrthancDicomWeb"` to the
  `Plugins` array in `orthanc.json` and restart. Verify with
  `curl http://localhost:8042/dicom-web/studies` — should return `[]` or
  a study list, **not** 404.
- Slicer's `/exec` enabled (the default). Check with:
  `slicer-cli --json doctor | jq '.checks[] | select(.name=="power-tool-endpoint")'`.

## End-to-end recipe

> **PHI / UID note.** Real DICOM `StudyInstanceUID` /
> `SeriesInstanceUID` / `SOPInstanceUID` values are HIPAA-relevant
> identifiers. Use placeholders below; substitute UIDs from the user's
> own Orthanc store. The `--patient` filter is exact-match on the MRN,
> not a name substring.

```bash
STUDY="<your-study-instance-uid>"
SERIES="<your-series-instance-uid>"
SOP="<your-sop-instance-uid>"
MRN="<your-patient-mrn>"

# 1. Pull from Orthanc into Slicer's DICOM database.
slicer-cli --json dicom pull \
  --orthanc http://localhost:8042 \
  --study "$STUDY"
# → {"ok": true, "imported_count": 1, "study_uid": "..."}

# 2. QIDO: confirm Slicer now sees the study (filter by MRN if useful).
slicer-cli --json dicom studies --patient "$MRN" \
  | jq '.studies[] | {patient_name, study_date, study_description}'

# 3. List series in the study.
slicer-cli --json dicom series "$STUDY" \
  | jq -r '.series[].series_uid'

# 4. List instances in the series.
slicer-cli --json dicom instances "$STUDY" "$SERIES" \
  | jq -r '.instances[].sop_uid'

# 5. WADO-RS retrieve the file.
slicer-cli --json dicom instance "$STUDY" "$SERIES" "$SOP" --out /tmp/cxr.dcm
head -c 132 /tmp/cxr.dcm | tail -c 4    # → "DICM" magic at byte 128

# 6. Full DICOM JSON metadata at any level.
slicer-cli --json dicom meta "$STUDY"
slicer-cli --json dicom meta "$STUDY" "$SERIES"
slicer-cli --json dicom meta "$STUDY" "$SERIES" "$SOP"
```

## Why `dicom pull` routes through `/exec`

Slicer's native `accessDICOMwebStudy` endpoint has a Python bug
(`request["dicomWEBPrefix"]` crashes on a typo in the handler). The CLI
templates the equivalent `DICOMUtils.importFromDICOMWeb(...)` call
through `/slicer/exec` instead. Consequence:

- `dicom pull` requires `/exec` to be enabled in Slicer's WebServer
  module.
- Each `dicom pull` invocation writes one line to the audit log.

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `E_HTTP_5XX` with body containing `unknown command "b'/exec'"` | `/slicer/exec` disabled in Slicer | enable in WebServer settings, or load the study via Slicer's GUI |
| Python error in `/exec` response mentioning `dicomWebEndpoint` or `accessToken` | Slicer build's `DICOMUtils.importFromDICOMWeb` has a different signature | introspect with `slicer-cli api raw POST /slicer/exec --body @- --confirm <<<'help(DICOMUtils.importFromDICOMWeb)'` |
| `dicom studies` returns `[]` after a successful `pull` | filter mismatch (wrong MRN) or DB caching | drop `--patient`, then re-filter from the full result |
| 404 on Orthanc `/dicom-web/...` | OrthancDicomWeb plugin not loaded | install + add to `Plugins` array in `orthanc.json` |
| `dicom pull` for an already-imported study | nothing — it's idempotent | re-running is safe; Slicer dedupes |

## Pointer

The full surface and rationale lives in
`docs/Slicer-CLI-UserManual.md` §5.7 and the surface report at
`docs/3d-slicer-webserver-surface-report.md` (which documents the
`accessDICOMwebStudy` bug we route around).
