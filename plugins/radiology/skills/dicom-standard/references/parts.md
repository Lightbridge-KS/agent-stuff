# The parts of DICOM PS3 — which one to pull

One line per part: what lives there and the questions it answers. Sizes are the DocBook XML
(2026d); at ~50 KB/s the two big ones take 10–20 minutes — run those pulls in the background.

| Part | Title | Pull it for | XML |
|---|---|---|---|
| PS3.1 | Introduction and Overview | scope, how the parts relate, glossary of DICOM terms | 0.1 MB |
| PS3.2 | Conformance | conformance statement structure and templates (Annex A–D), what a vendor must declare | 4.6 MB |
| PS3.3 | Information Object Definitions | IODs, modules and their attribute tables (Annex A composite IODs, Annex C modules), Type 1/2/3, enumerated values, SR document content | 24 MB |
| PS3.4 | Service Class Specifications | Storage, Query/Retrieve (C-FIND keys, Annex C), Worklist, MPPS, Storage Commitment, SOP Class UIDs per service | 4.4 MB |
| PS3.5 | Data Structures and Encoding | VRs (6.2), encoding rules, transfer syntaxes (Annex A), character sets, pixel data encapsulation, UIDs | 1.0 MB |
| PS3.6 | Data Dictionary | every data element: tag, name, keyword, VR, VM, retired (Table 6-1); file meta (7-1); directory structuring (8-1); registry of UIDs (Annex A) — the `tag` verb reads this part | 9.2 MB |
| PS3.7 | Message Exchange | DIMSE services and protocol (C-STORE, C-FIND …, N-*), command set, status codes (Annex C) | 0.8 MB |
| PS3.8 | Network Communication Support | association negotiation, PDUs, A-ASSOCIATE items, ARTIM, port | 0.4 MB |
| PS3.10 | Media Storage and File Format | DICOM file format, preamble, file meta information, DICOMDIR concepts | 0.2 MB |
| PS3.11 | Media Storage Application Profiles | CD/DVD/USB profiles (STD-GEN-CD …), what a profile requires | 0.5 MB |
| PS3.12 | Media Formats and Physical Media | physical media and file systems for interchange | 0.2 MB |
| PS3.14 | Grayscale Standard Display Function | GSDF, display calibration, JND | 0.9 MB |
| PS3.15 | Security and System Management Profiles | TLS/secure transport, audit trail messages (Annex A), **de-identification: Annex E, Table E.1-1 (attribute actions) and E.3 options**, digital signatures, Annex F–H system management | 3.4 MB |
| PS3.16 | Content Mapping Resource | templates (TID), context groups (CID), code sets — huge; pull only when a TID/CID question is at hand | 54 MB |
| PS3.17 | Explanatory Information | informative annexes: worked examples, rationale, use cases | 15 MB |
| PS3.18 | Web Services | DICOMweb: WADO-RS, STOW-RS, QIDO-RS, UPS-RS, URI/URL conventions, media types | 2.0 MB |
| PS3.19 | Application Hosting | hosted application API | 0.3 MB |
| PS3.20 | Imaging Reports using HL7 CDA | CDA report templates | 1.7 MB |
| PS3.21 | Transformations between DICOM and other Representations | SR ↔ FHIR / CDA mappings | 1.0 MB |
| PS3.22 | Real-Time Communication | DICOM-RTV (SMPTE ST 2110) | 0.1 MB |

Not published as DocBook (not pullable): PS3.9 and PS3.13 are retired.

Pull size vs. question — the cheap set that answers most clinical-informatics questions is
**15 + 6 + 5** (~14 MB); add **3** for IOD/module work and **4** for service-class details.
