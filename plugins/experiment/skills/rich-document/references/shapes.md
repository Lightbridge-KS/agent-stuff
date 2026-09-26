# Shapes — the smallest view that shows the point

Pick one shape per idea, place it beside the sentence it supports, and keep only
the calls, files, states, and boundaries the reader needs. One or two shapes per
explanation is typical; the whole catalog never. Text shapes are plain fences and
work in chat; Mermaid works only in a rich document.

## Text shapes (chat or document)

**Logic or an algorithm** → pseudocode:

```text
on save(content)
  if content unchanged
    return cached
  write content
  return fresh
```

**Runtime control flow** → call tree:

```text
present(source)
  parse_source
    validate_profile
  build
    stage_assets
    render_quarto
  publish
  start_viewer
```

**A surface** (CLI commands, a class's API, a UI) → tree with the owning file:

```text
rich_document.py              (scripts/)
  present SOURCE              --no-open --no-save --json
  open ARTIFACT_ID
  list --limit N
  stop ARTIFACT_ID
```

**Responsibilities or a broad refactor** → shallow file tree, one comment each:

```text
scripts/
├── rich_document.py   # CLI dispatch and output
├── rd_core.py         # validate, render, publish
└── rd_viewer.py       # loopback delivery
```

**A whole block** → verbatim, only when most of it is new, when trimming would
hide ownership or order, or when the reader needs a copyable target shape:

```python
def expand_skill(command: str) -> str:
    """Turn `/name` into the instruction the agent reads."""
    return f"use the {command[1:]} skill"
```

## Diff of a shape

When the point is *what changed* and the surrounding shape already exists, show
the shape as a `diff`. Match the diff to the topic, not to the source files.

Call-tree change:

```diff
 present(source)
   parse_source
+    check_mermaid_syntax
   build
-  open_browser
+  start_viewer
+    health_probe
```

File-layout change:

```diff
 scripts/
 ├── rich_document.py
-└── server.py
+├── rd_core.py         # split out of the CLI
+└── rd_viewer.py
```

Control-flow change:

```diff
 on present(source)
-  render
+  validate
+  if invalid: return diagnostics
+  render
   publish
```

## Mermaid (document only)

**Interaction, control flow, or data flow across parts** → a `{mermaid}` fence.
The terminal cannot render it, so a Mermaid diagram is by itself a reason for a
rich document; in chat, downgrade to a call tree.

````markdown
```{mermaid}
sequenceDiagram
    participant Agent
    participant CLI
    participant Viewer
    Agent->>CLI: present source.qmd
    CLI->>Viewer: start, health probe
    CLI-->>Agent: url, artifact id
```
````

## Blocks that carry a shape

| Need | Block |
|---|---|
| Variants of one thing (current vs proposed, per-language examples) | Tabset, one shape per tab |
| Two things side by side (two owners, before and after) | Columns |
| A caveat or tradeoff | Callout; `collapse="true"` for background the reader may skip |
| Something to copy | Ordinary code fence |

## Rules

- Smallest view that makes the point; next to the text it supports.
- A tabset compares variants of one thing; columns pair two different things.
- Paths are repo-relative. No machine names, home-directory paths, or site
  hostnames in a tree or an output: use a stand-in.
