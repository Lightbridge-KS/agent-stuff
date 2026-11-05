---
summary: Audit an existing DSH skill registry without expanding manifest-controlled vendored delivery.
read_when:
  - changing skill-vendor registry scanning or DSH delivery
---

# Audit DSH independently of vendored delivery

Date: 2026-11-05
Status: Accepted

DSH receives authored skills from the public and private content trees through
the installer's `dsh` target. Its registry must satisfy the symlink-only policy,
but adding that registry to vendored delivery defaults would also require every
manifest entry there.

All-entry `doctor` and `list` therefore scan `~/.dsh/skills` when it exists.
Absent DSH registries are optional. The scan does not create paths or alter
manifest entries. Names managed in other registries are not exempt in this
audit-only registry. When DSH is in the manifest's default registry list, normal
managed-entry assessment takes precedence. Per-entry registry overrides retain
their existing behavior. Named-entry checks continue to skip registry scanning.

Vendored delivery remains opt-in through the manifest. Changing default delivery
was rejected because authored harness support does not establish vendored skill
compatibility or authorize installing every vendored skill there.
