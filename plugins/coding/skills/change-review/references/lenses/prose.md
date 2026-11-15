# Lens: prose

Is the human-facing prose that the candidate adds or changes free of AI writing
patterns?

Read the `unslop` skill file named in the packet. Its *Scope* section decides which
files count, and its numbered rules are the patterns. Without that file, return
`Skipped: unslop skill not available`.

- Review only the lines the candidate adds or changes, in files inside that scope.
  Agent-facing files and working records are out, however they read. No file in
  scope: return `Skipped: no human-facing prose changed`.
- Detect only. The rewrite goes in the finding as the smallest correction.
- Report one finding per rule per file: the rule number, up to three quoted
  instances, and a count of the rest.
- A style the repository documents overrides a rule. Leave code, command output, and
  quoted text alone.

Impact is low. Use medium only when the pattern changes what the text claims: a
vague attribution, or a conclusion with no fact behind it.

Evidence: the quoted text and the rule number.
