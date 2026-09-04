# Shapes — what each rung looks like in code

Minimal, runnable Python sketches of the three plugin archetypes and the in-process
extension seam, for design mode: cite the matching shape, adapt its names, do not invent a
fifth. Every sketch was executed as written (2026-09-04); each ends with the observable
property that defines the shape. Rungs 1–3 are one paragraph each — they are ordinary and
you know them.

## Rungs 1–3 in one breath

- **Runtime config (1):** a typed settings object with a precedence chain
  `defaults → file → env → CLI`, one schema, one validation point, and an explicit answer
  to "hot reload or restart?". Nothing else.
- **Declarative composition (2):** a data file the core *interprets*: `pipeline: [load,
  denoise, segment]` or a rule expression `Modality == 'SEG'`. The core owns the
  vocabulary; the operator composes. When you catch yourself adding `if/else` to the
  interpreter per customer, you have hit the rung's ceiling.
- **Hooks (3):** `host.on("before_save", fn)`. The design work is the **event taxonomy by
  power** (observe · transform · chain · veto · replace) and the error posture per class —
  see the extension sketch below for the fail-closed veto.

## Rung 4a — Merged (3D Slicer)

The plugin is indistinguishable from core: same base class, same factory, same process.
"Installing" appends a directory to a search-path list read once at startup.

```python
# MERGED — no plugin API exists; the extension is merged into the ordinary module factory.
import importlib.util, pathlib

class Module:                        # the SAME base class core modules use
    name: str
    def setup(self, app): ...        # registers node types, readers, views…

class App:
    def __init__(self, search_paths: list[pathlib.Path]):
        self.modules: dict[str, Module] = {}
        self.search_paths = search_paths            # core dirs + extension dirs, read ONCE

    def load_all(self):                              # runs at startup, hence "restart required"
        for d in self.search_paths:
            for f in sorted(d.glob("*.py")):
                spec = importlib.util.spec_from_file_location(f.stem, f)
                mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
                m: Module = mod.MODULE                # convention, not contract
                m.setup(self); self.modules[m.name] = m

# "Installing an extension" = append its directory to search_paths in a settings file.
# The factory cannot tell core from extension, and nothing asks.
```

Defining property: `App` has no word for "extension". Power is maximal (an extension can
register anything core can), isolation is zero, lifecycle is restart-driven, and
compatibility must be paid by *rebuilding per host revision* (decision 6).

## Rung 4b — Registered (OpenClaw, MONAI Deploy)

In-process, but core reads **only the registry**. Manifest is read before any plugin code
runs; the contract is a bag of optional adapters; core branches on capability flags, never
on plugin id; failures become diagnostics, never crashes.

```python
# REGISTERED — manifest-first load, one-way flow into a registry, capability dispatch.
import json, importlib.util, pathlib
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class ChannelPlugin:                                  # the contract: a bag of OPTIONAL adapters
    id: str
    capabilities: set[str] = field(default_factory=set)
    send_text: Callable[[str, str], None] | None = None   # the only mandatory adapter
    send_rich: Callable[[str, dict], None] | None = None

class Registry:
    def __init__(self): self.channels: dict[str, ChannelPlugin] = {}; self.diagnostics: list[str] = []
    def register_channel(self, p: ChannelPlugin):
        if p.id in self.channels: self.diagnostics.append(f"duplicate id {p.id}"); return
        self.channels[p.id] = p

def load(plugin_dirs: list[pathlib.Path], reg: Registry):
    for d in plugin_dirs:
        manifest = json.loads((d / "plugin.json").read_text())      # 1. metadata, NO code run
        if manifest.get("kind") != "channel": reg.diagnostics.append(f"{d.name}: unsupported kind"); continue
        spec = importlib.util.spec_from_file_location(manifest["id"], d / manifest["entry"])
        mod = importlib.util.module_from_spec(spec)
        try: spec.loader.exec_module(mod); mod.register(reg)         # 2. plugin → registry, one way
        except Exception as e: reg.diagnostics.append(f"{d.name}: {e}")   # 3. diagnostic, never a crash

def deliver(p: ChannelPlugin, peer: str, text: str, rich: dict | None):
    if rich and "rich_text" in p.capabilities and p.send_rich:       # branch on CAPABILITY, never on id
        return p.send_rich(peer, rich)
    return p.send_text(peer, text)                                    # graceful degradation
```

A plugin directory is `plugin.json` + `channel.py` whose `register(reg)` calls
`reg.register_channel(ChannelPlugin(...))`. Defining property: core never imports a plugin
by name and never special-cases one; the manifest is inspectable with zero code executed.
What the type system cannot enforce (optional adapters behaving consistently) **contract
test suites** must (decision 9).

## Rung 4c — Hosted (VS Code)

Plugin code runs in another process. The manifest is read before any plugin code runs, and
the deeper property is that **activation events are derived from contributions** (declaring
a command implies "wake me when it is invoked"); every call across the wall is asynchronous
and serialisable.

```python
# HOSTED — declarative half read by the host; dynamic half behind async RPC over stdio.
import asyncio, json, sys

class Host:
    def __init__(self, manifest: dict):
        self.commands = {c["id"]: c["title"] for c in manifest["contributes"]["commands"]}  # UI ready, no code run
        self.activation_events = {f"onCommand:{c}" for c in self.commands}                   # implicit derivation
        self.proc: asyncio.subprocess.Process | None = None
        self._id = 0

    async def activate(self, entry: str):                                # runs once, on first event
        self.proc = await asyncio.create_subprocess_exec(sys.executable, entry,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        await self.call("activate", {})

    async def call(self, method: str, params: dict):                     # the ONLY way in: async, serialisable
        self._id += 1
        self.proc.stdin.write((json.dumps({"id": self._id, "method": method, "params": params}) + "\n").encode())
        await self.proc.stdin.drain()
        return json.loads(await self.proc.stdout.readline())["result"]

    async def execute_command(self, cmd: str):
        if f"onCommand:{cmd}" in self.activation_events and self.proc is None:
            await self.activate("plugin_main.py")
        return await self.call("executeCommand", {"id": cmd})
```

```python
# plugin_main.py — the other process. It has no handle to the host's UI;
# an infinite loop here cannot freeze the host.
import json, sys
handlers = {}
def activate(_): handlers["hello.say"] = lambda: "hello from the extension host"; return "ok"
for line in sys.stdin:
    req = json.loads(line)
    result = activate(req["params"]) if req["method"] == "activate" else handlers[req["params"]["id"]]()
    sys.stdout.write(json.dumps({"id": req["id"], "result": result}) + "\n"); sys.stdout.flush()
```

Defining property: `Host.commands` is populated before `plugin_main.py` exists as a
process. Costs: no synchronous API ever; anything the plugin contributes must be
expressible as data or reachable by message. In a typed language, make the async-only rule
a *type error* (a mapped type that rewrites every proxy method to return a promise).
Placement does **not** decide change landing (decision 5): a hosted seam may still require
a restart, and a merged one may in principle hot-swap; live install follows from
delta-based registries, which the hosted shape merely makes easy.

## Rung 5 — In-process extension (pi, Emacs)

The file is the extension. It receives the whole host API and may **replace** built-ins.
Veto hooks deliberately have no `try/except`: a crashing gate blocks. Reload is an explicit
act and the transcript survives it — which is what lets an agent inside the host write an
extension and use it in the same session.

```python
# IN-PROCESS EXTENSION — whole host API handed over; rewrite allowed; vetoes fail closed.
import importlib.util, pathlib
from dataclasses import dataclass

@dataclass
class ToolCall: name: str; args: dict
@dataclass
class Veto: reason: str

class HostAPI:                                        # handed whole to every extension
    def __init__(self): self.tools: dict = {}; self.hooks: dict[str, list] = {"tool_call": [], "turn_end": []}
    def register_tool(self, name, fn): self.tools[name] = fn          # add — or REPLACE a built-in
    def on(self, event, handler): self.hooks[event].append(handler)

class Host:
    def __init__(self, ext_dir: pathlib.Path): self.ext_dir = ext_dir; self.transcript: list[str] = []; self.reload()

    def reload(self):                                  # explicit act, never a file watcher; transcript survives
        self.api = HostAPI()
        for f in sorted(self.ext_dir.glob("*.py")):
            spec = importlib.util.spec_from_file_location(f.stem, f)
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            mod.setup(self.api)                        # default export: factory receiving the host API

    def run_tool(self, call: ToolCall):
        for h in self.api.hooks["tool_call"]:          # VETO class: deliberately no try/except —
            r = h(call)                                # a crashing gate must block, not pass (fail closed)
            if isinstance(r, Veto): return f"blocked: {r.reason}"
        out = self.api.tools[call.name](**call.args)
        for h in self.api.hooks["turn_end"]:           # OBSERVE class: isolated, fail open
            try: h(call, out)
            except Exception: pass
        self.transcript.append(out); return out
```

```python
# ~/.app/extensions/gate.py — written by a human, or by the agent running inside the host
from extension import Veto
def setup(api):
    api.register_tool("shout", lambda text: text.upper())
    api.on("tool_call", lambda call: Veto("no writes outside repo")
           if call.name == "write" and ".." in call.args.get("path", "") else None)
```

Defining property: `gate.py` imports the host module itself, not an SDK, and can replace
`write` outright. Trust is binary; the controls are admission-shaped (who may drop a file
here, who may call `reload`), never containment-shaped.

## Choosing between the shapes

| You need… | Shape |
|---|---|
| plugins as capable as core, authors you trust, restart acceptable | **Merged** |
| many providers behind one contract, in-process is fine, policy must stay uniform | **Registered** |
| untrusted third parties, the host must never freeze, live install | **Hosted** |
| a trusted operator (or agent) to *rewrite* behaviour with zero friction | **Extension** |
| third parties to ship prompts, hooks, and config together, with no code | **Bundle** — a manifest over lower-rung artifacts (decision 1 pole); no sketch needed, the artifacts are rungs 1–3 |
| none of the above — the variation is values or composition | **stay on rung 1–2** |
