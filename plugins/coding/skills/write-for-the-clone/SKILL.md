---
name: write-for-the-clone
description: >-
  Make durable repository documentation usable without the original session when
  writing or reviewing agent instructions, README files, docs, or runbooks.
metadata:
  version: "2026-10-27"
---

# Write for the clone

Write for a future reader arriving without the author's machine or conversation.
Durable claims need enough context to interpret and use them: scope,
prerequisites, and a version or date when relevant. They need not be true for every
reader forever.

## Put each fact at its scope

Follow the repository's existing documentation structure. Standing rules belong
in agent instructions; settled explanations in design docs; milestones and evidence
in progress trackers; engineering issues in the issue tracker; personal setup in
the appropriate local configuration. Do not turn a session observation into a
standing instruction or discard useful progress merely because it changes.

Explicitly scoped platform or device documentation is valid when that is the
repository's purpose and disclosure rules permit it. This is not permission to
copy the author's environment into an unrelated project.

## Remove dependence on the original context

- **Where:** use working relative links for repository files and state the working
  directory for commands when it matters. For external resources, name the actual
  supported input or configuration mechanism, how it is supplied, and any required
  access or setup. Replacing a personal path with `~/data` or an unexplained
  placeholder does not make an instruction usable.
- **Who:** replace "my setup" and "ask me" with explicit prerequisites, roles,
  or an ownership reference. Keep personal preferences out of shared product
  instructions unless they are an adopted project convention.
- **When:** anchor changing claims to a date, version, or revision when needed.
  "Tests passed at commit ... in environment ..." is evidence; "tests pass" can
  be mistaken for a continuing guarantee. Keep current guidance distinct from
  historical observations.
- **State:** put unfinished work and known failures in their existing tracker,
  with enough context to resume or verify them. Link from standing guidance only
  when the limitation affects the reader's task.

## Keep instructions grounded

Check that named commands, files, links, and configuration inputs exist and behave
as described. Writing "set `DATA_DIR`" is not a fix if the program never reads it.
In a documentation-only task, identify the implementation gap; do not invent an
interface or silently expand the task into a code change.

Point to authoritative definitions instead of copying volatile settings. Prefer
existing setup and task commands over duplicating their internals, while retaining
the explanation and examples a reader needs. Automate recurring fragile steps when
that earns its maintenance cost; not every prose instruction needs a new script.

## Apply proportionately

Scratch notes and illustrative toys may retain local context. Reassess when they
become reusable operational guidance; a kept toy alone does not require production
setup. Existing secrets and data-handling rules still apply.

Review from the intended reader's starting point: can the reader resolve each
reference and follow the instructions with the declared prerequisites? Verify
relevant links and safe commands; distinguish reviewed instructions from executed
checks. This lens creates no mandatory report, lint tool, or documentation rewrite.
