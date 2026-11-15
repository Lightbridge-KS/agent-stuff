# Lens: correctness

Does the candidate do what it intends, without breaking what it touches?

- Follow each changed behaviour to its callers and consumers in the candidate tree. A
  changed interface with an unchanged caller is the common miss.
- Include failure paths the change adds or alters, and tests that can no longer fail
  or no longer exercise the changed behaviour.
- Instruction files (skills, agent definitions, prompts) are behaviour: look for
  contradictions, steps that cannot be run as written, and references to files or
  commands the candidate does not contain.
- Security regressions count: injection, missing authorization, exposed secrets.

Skip style, naming, speculative hardening, performance with no stated consequence,
and anything the repository's own lint or type gates catch.

Evidence: the path that fails — the input or state, the lines it passes through, the
wrong result. When only a run can establish it, put the focused check under
questions; do not assert it as a finding.
