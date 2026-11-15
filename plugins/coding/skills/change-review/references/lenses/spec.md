# Lens: spec

Does the candidate implement what the spec in the packet asked for?

Report three kinds of finding:

- **Missing** — a requirement the spec states that the candidate omits or covers in
  part.
- **Unrequested** — behaviour in the candidate that the spec did not ask for.
- **Wrong** — a requirement that looks implemented but does not behave as the spec
  says.

Approved constraints in the packet count as spec. The intended outcome alone does
not: without spec text, return `Skipped: no spec available`.

Judge the candidate against the spec, not the spec itself. A contradiction or gap in
the spec goes under questions.

Evidence: the quoted spec line, and the candidate lines that omit, exceed, or
contradict it.
