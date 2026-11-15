# Reviewer contract

For the reviewer agent (`change-reviewer` on Claude Code; `change-reviewer-codex`
or `change-reviewer-codex-docs` on Codex). Its definition sets the authority; this
file sets the input, the method, and the return.
The main agent owns decisions, fixes, verification, and delivery.

## Input

- Repository location.
- Base object ID and candidate tree ID.
- Intended outcome, approved constraints, relevant design references.
- Assigned lenses, with the path to each lens file.
- Lens inputs: both reproducibility skill files; the spec text or path.
- On a re-review: the previous candidate ID, and the prior findings with their
  dispositions.

Read every assigned lens file first. A missing input, an unreadable path, or an
object that does not resolve makes the review partial: say what is missing and
review what remains.

## Review the candidate

- Compare the supplied objects with
  `git diff --no-ext-diff --no-textconv <base> <candidate>`. Read file contents with
  `git show <candidate>:<path>`, new files included. Do not substitute the working
  tree or the index for the supplied snapshot.
- Trace into surrounding code, setup commands, configuration, and documentation in
  the candidate tree when a finding depends on them.
- Report problems the change introduces, worsens, or exposes. This is not an audit of
  unrelated existing issues.
- Apply each assigned lens in turn and keep its findings apart. A finding that fits
  two lenses goes under the one whose evidence is stronger, once.
- On a re-review, compare the previous candidate with the new one. Apply every
  assigned lens to that difference, and confirm each finding marked fixed. Do not
  repeat a finding that was dismissed with evidence unless the candidate now
  contradicts that evidence.

## Findings

Report concrete defects supported by evidence. Each finding has:

- An identifier `<lens>-<n>` and an impact: high, medium, or low.
- Candidate file and line, with supporting references when needed.
- The defect.
- The evidence the lens asks for.
- The consequence, and who or what it affects.
- The smallest correction, or a focused check when only execution can establish it.

Leave out speculation, style preferences, duplicates, and demands for configuration
nobody needs. No findings is a valid result.

## Return

1. **Coverage:** complete or partial; base and candidate IDs; lenses assigned; scope
   inspected.
2. **One section per assigned lens**, in the order assigned. Each ends in findings
   ordered by impact, `No findings within the reviewed scope.`, or
   `Skipped: <reason>`.
3. **Questions and limitations:** unresolved questions, and checks that need
   execution.

Complete means the requested scope was inspected. It does not certify the repository
or replace tests. Keep the report concise; omit raw diffs and logs.
