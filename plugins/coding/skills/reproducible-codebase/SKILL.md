---
name: reproducible-codebase
description: >-
  Remove hidden local-environment dependencies when writing, changing, or reviewing
  maintained code and scripts, or promoting experiments into maintained use.
metadata:
  version: "2026-10-27"
---

# Reproducible codebase

Make maintained code runnable without the author's unstated local context. Remove
accidental environment dependence with the smallest change that preserves intended
behavior. Work within the project's declared environments; reproducibility does
not automatically require every OS, containers, or identical output bytes.

## Scope by intended use

Apply to maintained source, scripts, tests, and build or setup commands. Directory
names are clues, not the decision: a reusable script can live outside `scripts/`.

Scratch spikes, toy examples, `_playground/`, and OS temporary files may use local
shortcuts to answer a narrow question or demonstrate a mechanism. A kept toy still
does not need production configuration machinery. Reassess shortcuts when the work
becomes a maintained dependency, reusable tool, or operational instruction.
Existing secrets and data-handling rules still apply.

## Expose the assumptions

- **Dependencies:** inspect reliance on shell initialization, global tools,
  sibling checkouts, ignored files, caches, local data, credentials, and running
  services. Declare what is required through the existing manifests, locks,
  setup commands, fixtures, and external prerequisites. A warm cache or installed
  tool is not evidence that setup is complete.
- **Paths:** choose an explicit base: repository, package resources,
  configuration file, or caller input. A relative string alone does not remove
  working-directory dependence; replacing a personal path with a home-relative
  path may preserve the same hidden assumption. A documented "run from repository
  root" command is valid. Absolute paths supplied by callers can be valid too.
- **Inputs:** when results depend on data, model versions, randomness, or external
  state, identify which inputs must be controlled for the intended claim. Do not
  promise determinism from a seed alone.

## Bind values at the smallest sufficient boundary

Ask who must choose a value and when. Keep stable domain decisions in code; name
constants when that clarifies their meaning. Use parameters for caller choices,
and group related configuration only when useful. Deployment differences use the
project's existing file, environment, CLI, or secret-provider boundary. Dynamic
configuration needs a demonstrated runtime requirement.

Parse and validate external configuration at the entry or assembly boundary; pass
resolved values inward. Preserve established precedence and defaults. Moving a
literal into a constant does not remove an environment dependency, and inventing
an environment variable without wiring it into execution does not fix one.

## Verify the changed assumption

Choose evidence that exercises the dependency: a relocated checkout, supported
invocation locations, a clean setup, or representative explicit inputs. State the
environment and checks actually exercised; a local pass does not establish every
supported platform. Keep verification proportional to the change. Follow existing
tooling and delivery workflows; this lens adds no mandatory artifact or migration.
