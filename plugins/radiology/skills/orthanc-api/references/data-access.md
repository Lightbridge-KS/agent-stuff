# Data Access — Local Resources

Working with DICOM data already stored in Orthanc: getting it in, navigating it,
reading tags, downloading it in various forms, searching the local database, and
mutating it. All examples assume the `BASE`, `AUTH`, and `S` (session) setup from
`SKILL.md`.

## Contents

1. [Uploading DICOM](#1-uploading-dicom)
2. [Browsing the hierarchy](#2-browsing-the-hierarchy)
3. [Reading DICOM tags](#3-reading-dicom-tags)
4. [Downloading images & files](#4-downloading-images--files)
5. [Decoding to NumPy (AI pipelines)](#5-decoding-to-numpy-ai-pipelines)
6. [Downloading studies, PDFs, videos](#6-downloading-studies-pdfs-videos)
7. [Finding local resources (`/tools/find`)](#7-finding-local-resources-toolsfind)
8. [Looking up by DICOM UID (`/tools/lookup`)](#8-looking-up-by-dicom-uid-toolslookup)
9. [Anonymize & modify](#9-anonymize--modify)
10. [Deleting resources](#10-deleting-resources)

---

## 1. Uploading DICOM

POST the raw bytes of a `.dcm` file, or a `.zip` of many files, to `/instances`.
Orthanc returns the Orthanc IDs of the created instance and its parents.

`curl` is clearest for raw binary. Setting an empty `Expect:` header noticeably
speeds up POSTs:

```bash
curl -X POST -H "Expect:" http://localhost:8042/instances --data-binary @CT.dcm
curl -X POST -H "Expect:" http://localhost:8042/instances --data-binary @archive.zip
```

In Python:

```python
with open("CT.dcm", "rb") as f:
    r = S.post(f"{BASE}/instances", data=f.read())
r.raise_for_status()
print(r.json())
# {"ID": "5d4a3991-...", "ParentPatient": "...", "ParentSeries": "...",
#  "ParentStudy": "...", "Path": "/instances/5d4a3991-...", "Status": "Success"}
```

To recursively import a folder, walk it and POST each file (or zip first and POST
once). Orthanc's source ships `ImportDicomFiles.py` and the more capable
`OrthancImport.py` (handles `.zip`/`.tar.gz`/`.tar.bz2`) as samples.

## 2. Browsing the hierarchy

List IDs at a level, then fetch one resource to get its `MainDicomTags` plus links
to parent and children.

```python
S.get(f"{BASE}/patients").json()    # ["07a6ec1c-...", ...]
S.get(f"{BASE}/studies").json()
S.get(f"{BASE}/series").json()
S.get(f"{BASE}/instances").json()

study = S.get(f"{BASE}/studies/{study_id}").json()
study["Series"]          # child series IDs (array)
study["ParentPatient"]   # parent patient ID
study["MainDicomTags"]   # {"StudyInstanceUID","StudyDate","StudyDescription",...}
```

A series object also reports `ExpectedNumberOfInstances` and a `Status`
(`Complete`/`Missing`/...), useful for detecting partial transfers. An instance
object reports `FileSize`, `FileUuid`, and `IndexInSeries`.

Convenience parent/child shortcuts exist at every level, e.g.
`GET /instances/{id}/study`, `/instances/{id}/patient`, `/series/{id}/instances`,
`/studies/{id}/series`. See `references/endpoints.md`.

## 3. Reading DICOM tags

Three views of an instance's tags, in increasing rawness:

```python
# Human-readable: {"PatientName": "...", "StudyDate": "...", ...}
S.get(f"{BASE}/instances/{iid}/simplified-tags").json()

# Detailed: keyed by hex group/element with VR + value type info
S.get(f"{BASE}/instances/{iid}/tags").json()

# Raw single tag by hex (group-element); returns the bare value, not JSON
S.get(f"{BASE}/instances/{iid}/content/0010-0010").text   # → "DOE^JOHN"

# List every available raw tag
S.get(f"{BASE}/instances/{iid}/content").json()
```

Sequences are explored by descending into them positionally:

```python
# Open sequence 0008-1250 → child 0 → sequence 0040-a170 → child 0 → tag 0008-0104
S.get(f"{BASE}/instances/{iid}/content/0008-1250/0/0040-a170/0/0008-0104").text
```

At study/series level, `/shared-tags` returns tags common to all children, and
`/studies/{id}/instances-tags` dumps tags of every child instance at once.

## 4. Downloading images & files

```python
# Raw DICOM file
open("Instance.dcm","wb").write(S.get(f"{BASE}/instances/{iid}/file").content)

# 8-bit preview PNG, dynamic range stretched to [0..255] (good for thumbnails)
open("preview.png","wb").write(S.get(f"{BASE}/instances/{iid}/preview").content)

# JPEG preview via Accept header; quality is tunable
r = S.get(f"{BASE}/instances/{iid}/preview",
          headers={"Accept": "image/jpeg"}, params={"quality": 80})
```

For pixel-accurate PNGs **without** range stretching (values cropped to the target
bit depth), use the typed image routes:

```python
S.get(f"{BASE}/instances/{iid}/image-uint8")    # 8-bit PNG
S.get(f"{BASE}/instances/{iid}/image-uint16")   # 16-bit PNG
S.get(f"{BASE}/instances/{iid}/image-int16")    # signed pixel data
```

Multi-frame instances expose per-frame variants under
`/instances/{id}/frames/{frame}/...` (`preview`, `rendered`, `image-uint16`,
`numpy`, `raw`, etc.).

## 5. Decoding to NumPy (AI pipelines)

**≥ Orthanc 1.11.0.** Decode an instance or a whole series straight to a NumPy
array, even from compressed transfer syntaxes — no local DICOM decoder needed.

```python
import io, numpy as np

# One instance → shape (1, H, W, 1) grayscale  or  (1, H, W, 3) color
r = S.get(f"{BASE}/instances/{iid}/numpy"); r.raise_for_status()
arr = np.load(io.BytesIO(r.content))

# Whole series → shape (depth, H, W, channels); first axis = number of slices
r = S.get(f"{BASE}/series/{sid}/numpy"); r.raise_for_status()
vol = np.load(io.BytesIO(r.content))
```

By default values are floats with `Rescale Slope`/`Rescale Intercept` applied
(so CT comes back in Hounsfield units). Options:

- `?compress=1` — return a compressed `.npz` (array is named `arr_0` inside).
- `?rescale=0` — skip float conversion and rescale; return original integer voxels
  (smaller payload, raw stored values).

```python
r = S.get(f"{BASE}/series/{sid}/numpy", params={"rescale": 0, "compress": 1})
vol = np.load(io.BytesIO(r.content))["arr_0"]
```

## 6. Downloading studies, PDFs, videos

```python
# Whole study as a ZIP of DICOM files
open("Study.zip","wb").write(S.get(f"{BASE}/studies/{study_id}/archive").content)

# Whole study as a zipped DICOMDIR (media)
open("Media.zip","wb").write(S.get(f"{BASE}/studies/{study_id}/media").content)
```

For large archives, run as an async job via `POST /studies/{id}/archive` with
`"Synchronous": false` (see `references/jobs-and-changes.md`), or use
`/tools/create-archive` / `/tools/create-media` for a custom set of resources.

Encapsulated documents come out of their raw tag:

```python
# Embedded PDF (SOP Class 1.2.840.10008.5.1.4.1.1.104.1) lives in tag 0042,0011.
# The last byte may be a padding byte if the source PDF had odd length.
open("doc.pdf","wb").write(
    S.get(f"{BASE}/instances/{iid}/content/0042,0011").content)

# Or the convenience route:
open("doc.pdf","wb").write(S.get(f"{BASE}/instances/{iid}/pdf").content)

# Embedded video → raw bytes of frame 0 (confirm transfer-syntax UID metadata first)
open("clip.mp4","wb").write(S.get(f"{BASE}/instances/{iid}/frames/0/raw").content)
```

## 7. Finding local resources (`/tools/find`)

Searches **Orthanc's own database** (not a remote PACS — that's
`references/networking.md`). POST a `Level` and a `Query` of DICOM-tag matchers;
returns matching Orthanc IDs, or full objects with `"Expand": true`.

```python
hits = S.post(f"{BASE}/tools/find", json={
    "Level": "Study",                       # Patient | Study | Series | Instance
    "Query": {
        "PatientID": "*",                   # "" or "*" = match anything
        "StudyDescription": "*Chest*",      # case-insensitive wildcards by default
        "StudyDate": "20180323-",           # open-ended range (from this date on)
    },
    "Expand": True,
}).json()
```

Query value syntax mirrors DICOM C-FIND:

- `*` is a wildcard: `"Jones*"` (prefix), `"*Jo*"` (contains).
- Date ranges: `"20180323-"` (after), `"-20180325"` (before),
  `"20180323-20180325"` (between).
- A list of alternatives is backslash-separated: `"123\\abc"`.

Useful body fields:

- `"Limit": 4` — cap the number of results.
- `"RequestedTags": [...]` — **≥ 1.11.0**, requires `"Expand": true`. Returns tags
  not in MainDicomTags or that must be computed (e.g. `ModalitiesInStudy`,
  `NumberOfStudyRelatedSeries`) under a `RequestedTags` key.
- `"Labels": [...]`, `"LabelsConstraint": "Any"|"All"|"None"` — **≥ 1.12.0**.
- **≥ 1.12.5** (`ExtendedFind`; SQLite or PostgreSQL ≥ 7.0): `"OrderBy"` (sort by
  `DicomTag` or `Metadata`, `ASC`/`DESC`), `"MetadataQuery"`, `"ParentPatient"`,
  and `"ResponseContent": ["MainDicomTags","Metadata","Children","Labels","Attachments"]`.

```python
S.post(f"{BASE}/tools/find", json={
    "Level": "Study",
    "Query": {"StudyDate": "20200101-"},
    "OrderBy": [{"Type": "DicomTag", "Key": "StudyDate", "Direction": "ASC"}],
    "Labels": ["urgent"], "LabelsConstraint": "Any",
    "RequestedTags": ["PatientName", "ModalitiesInStudy",
                      "NumberOfStudyRelatedSeries"],
    "Expand": True,
})
```

`/tools/count-resources` (POST, same Query shape) returns just a count.

## 8. Looking up by DICOM UID (`/tools/lookup`)

The bridge from a DICOM UID back to Orthanc IDs. POST the UID as the body:

```python
matches = S.post(f"{BASE}/tools/lookup",
                 data="1.2.840.113704.1.111.7016.1342451220.40").json()
# [{"ID": "9ad2b0da-...", "Path": "/studies/9ad2b0da-...", "Type": "Study"}, ...]
```

## 9. Anonymize & modify

Both are POSTs at any level; both can run async. Anonymization follows DICOM
PS3.15 by default; you can override or keep specific tags.

```python
# Anonymize a study → creates a NEW anonymized study, returns its IDs
r = S.post(f"{BASE}/studies/{study_id}/anonymize", json={
    "Replace": {"PatientName": "ANON", "PatientID": "ANON001"},
    "Keep": ["StudyDescription"],
    "KeepPrivateTags": False,
    # "Synchronous": False,   # large studies: run as a job
})

# Modify in place / produce a modified copy
S.post(f"{BASE}/series/{series_id}/modify", json={
    "Replace": {"SeriesDescription": "Corrected"},
    "Remove": ["StationName"],
    "Force": True,   # required to change protected tags like SOP/Study UIDs
})

# Bulk variants over a heterogeneous resource set
S.post(f"{BASE}/tools/bulk-anonymize", json={"Resources": [id1, id2]})
S.post(f"{BASE}/tools/bulk-modify",    json={"Resources": [id1], "Replace": {...}})
```

The full anonymization rule set (tag groups removed, UID handling) is documented
on the Orthanc Book's Anonymization page; for AI work the key point is that
anonymize **creates new resources** with new Orthanc IDs and new SOP/Study UIDs.

## 10. Deleting resources

DELETE the resource URI at any level (cascades to children):

```python
S.delete(f"{BASE}/patients/{pid}")
S.delete(f"{BASE}/studies/{study_id}")
S.delete(f"{BASE}/series/{series_id}")
S.delete(f"{BASE}/instances/{iid}")
```

To delete an **unrelated** set in one call (**≥ 1.9.4**) — patients/studies/
series/instances that share no common parent:

```python
S.post(f"{BASE}/tools/bulk-delete",
       json={"Resources": ["b6da0b16-...", "d6634d97-..."]})
```
