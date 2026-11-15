# Lens: standards

Does the candidate follow what this repository documents about how its code and
documents are written?

Find the standards in the candidate tree: agent instruction files (`AGENTS.md`,
`CLAUDE.md`), `CONTRIBUTING.md`, a coding-standards or structure document, a
glossary of domain terms. Read them from the candidate, not the working tree. None
found: return `Skipped: no documented standards`.

- A breach of a documented rule is a finding. Say whether the rule is stated as
  mandatory or as a preference.
- Only what the repository documents counts. Do not import outside conventions or
  personal taste.
- Skip rules the repository's tooling enforces.
- When the candidate changes a standard, review the rest of the candidate against the
  new text, and note the change of standard under questions.

Evidence: the file and the quoted rule, and the candidate lines that break it.
