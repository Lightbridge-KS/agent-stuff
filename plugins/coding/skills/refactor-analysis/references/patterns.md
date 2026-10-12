# Design patterns as refactoring moves

A pattern shows up in a refactoring pass in two directions. **Collapse**: a classic class
hierarchy that a language feature now absorbs — flatten it. **Introduce**: an ad hoc shape
that a pattern would name and stabilize — only past the worth test and a real seam. Pattern
names survive the collapse: "pass a strategy", "add a middleware" still tell the reader what
the code is for. Use them on the card.

## 0. Procedure

1. **Recognize** the shape — by shape (§1) or by name (§2).
2. **Pick the direction.** Classic shape with verdict 🟢 or 🟡 → collapse candidate. Ad hoc
   shape a pattern would name → introduce candidate. Verdict ⚪ → leave; trim ceremony only.
3. **Apply the guard.** Collapse → the *keep classic when* column of §2. Introduce → the
   one-of rule and §3.
4. **Write the card.** Move = `Collapse <Pattern> into <family>` or `Introduce <Pattern> at
   <seam>`. *Earns it* cites a worth-test question; *Preserve* names the dispatch, ordering,
   or identity the pattern was guaranteeing.
5. **Proof.** A collapse that changes dispatch or construction order names the differential
   rung; an introduce that adds a seam names the architecture rung.

## 1. Recognition by shape

The language-neutral layer. Recognize the *shape*, not the class names.

| Feature family | The classic shape it absorbs | Patterns |
|---|---|---|
| First-class functions & closures | an interface with one method, implemented by classes whose constructors only hold configuration | Strategy, Command, Chain of Responsibility, Template Method, Adapter, Decorator, Factory Method, Abstract Factory |
| Immutable values & non-destructive copies | hand-written clone, copy-and-modify, or step-wise build over plain data | Builder, Prototype, Memento |
| Pattern matching over closed types | one operation spread across every class of a closed hierarchy, as per-class overrides or double dispatch | Visitor, Composite, State |
| Built-in events & streams | a hand-rolled subscriber list, or a hub that knows every colleague's type | Observer, Mediator |
| Generators | cursor classes with has-next / next and an index field | Iterator |
| Modules & visibility | a class whose only job is "exactly one instance" or "one entry point" | Singleton, Facade |
| Memoization | a factory whose only job is caching by key | Flyweight |
| Dynamic proxies | the same check repeated in every forwarding method | Proxy |

Only Bridge has no family behind it: holding an interface and delegating *is* composition.

## 2. Collapse table

Verdicts: 🟢 Replaces (the feature *is* the pattern; the classes disappear) · 🟡 Simplifies
(most classes go, the design idea stays) · ⚪ Still the idiom (only ceremony shrinks).
"Keep classic when" is the guard that blocks the collapse.

| Pattern | Verdict | Collapses into | Keep classic when |
|---|---|---|---|
| Factory Method | 🟡 | the factory passed in as a function; a registry map to pick by name | creator subclasses also override other workflow steps; a framework exposes creation as one of several hooks; creation needs state held by the creator |
| Abstract Factory | 🟡 | an immutable record of constructors; each family a preset | per-family logic or dependencies; families are runtime plug-ins that need a named type; the factory keeps shared state across its products |
| Builder | 🟡 | named and required constructor arguments plus non-destructive copy; director recipes as functions | construction is a multi-step *process* with parsing, I/O, or validation between steps; enforced step order; the object accumulates over time |
| Prototype | 🟢 | immutable values plus the language's copy-and-modify | the copy needs custom rules (fresh identity, reset counters); the object owns handles that must not be duplicated |
| Singleton | 🟢 | one module-level or static instance; a cached factory; a lifetime in the DI container when one exists | a second instance is a bug you must *prevent* (device handle, process-wide lock); a library with no composition root that must own its access point |
| Adapter | 🟡 | a function type for a single-operation target — a method reference *is* the adapter | multi-method target; state, caching, or error translation across calls; the adapter must be registered by type |
| Bridge | ⚪ | nothing — composition is the idiom; structural typing trims the ceremony | conformance must be enforced at runtime; the abstraction validates or wraps what it holds |
| Composite | 🟡 | plain immutable data plus pattern-matching functions — new operations cheap, new node types dear | node types are added often or by code you don't own; nodes change in place; each node carries its own behavior |
| Decorator | 🟡 | a value plus functions folded over it, when every layer only adds data | layers wrap live behavior (logging, caching, retry, access); a layer keeps state between calls; every call must pass through each layer |
| Facade | ⚪ | the module is the facade — visibility rules hide the subsystems; a stateless entry point is a function | the facade owns subsystem instances across calls; clients need several configured facades, or a mock one |
| Flyweight | 🟡 | a memoized factory over immutable values; the intrinsic/extrinsic split is still your design | pool management: weak references, exactly-once creation under concurrency, inspection or preloading |
| Proxy | 🟡 | one dynamic proxy that writes the check once; rules as a policy table | per-method logic; full static checking wanted; a hot path; a runtime without reflection |
| Chain of Responsibility | 🟢 | middleware functions taking (request, next), folded into a pipeline; reordering is list order | handlers need several methods or injected services; runtime insertion or inspection; exactly one handler must claim (a router is simpler) |
| Command | 🟡 | a pair of closures (do, undo); the invoker and its history stacks unchanged | commands must be serialized, named for menus or audit, or queued and handled elsewhere |
| Iterator | 🟢 | the built-in iteration protocol plus generators | peek, remove, reset; a resumable position (cursor, pagination token); a named cursor type across an API boundary |
| Mediator | 🟡 | a generic event bus — a mediator *without the brain*; the coordination rules move into the wiring and need one named home | a rule reads several colleagues' state at once; ordering, error handling, or rollback across steps matter |
| Memento | 🟡 | an immutable state value — every state is its own snapshot; the caretaker is a list | state holds uncopyable resources; the snapshot must stay opaque across a plugin boundary; delta or versioned save formats |
| Observer | 🟢 | built-in events or streams, or a list of callables; subscribe returns an unsubscribe | observers handle several notification kinds as one contract; registration and inspection by type; explicit delivery control (order, error isolation, weak refs) |
| State | 🟡 | an enum plus one transition table keyed by (state, action) | each state has rich behavior or data of its own, large enough for its own file and tests |
| Strategy | 🟢 | a function; configuration captured in a closure; a test double is a lambda | a family of related operations; identity needed (a name for logging or serialization); DI-constructed with its own dependencies; a runtime plug-in |
| Template Method | 🟡 | a function with step arguments; the hook is a default argument; variants are values | steps share state through the instance; a framework's lifecycle hooks *are* the API; many steps with defaults |
| Visitor | 🟢 | pattern matching over a closed, owned set with an exhaustiveness check | shapes come from code you don't own or from plug-ins; a visitor accumulates state over a large tree; elements must keep internals private |

## 3. Introduce guards

**The one-of rule:** a pattern introduced over a set of size one is a hypothetical seam.
One strategy, one product, one observer, one handler — no pattern; name the function and
move on. The rows below are the thresholds the one-of rule does not give.

| Pattern | Do not introduce when |
|---|---|
| Factory Method / Abstract Factory | creation is a plain constructor call; one product type; families rarely change |
| Builder | a few fields; one-step construction; named arguments already remove the pain |
| Singleton | the motive is convenience — inject instead; tests need isolated instances |
| Adapter | the interfaces already agree; you can change the source class |
| Decorator | one fixed configuration (inherit or compose once); callers need the unwrapped object |
| Facade | the subsystem is already small; it would become the god object that does everything |
| Flyweight | few objects, or little shared state; extrinsic state is costly to recompute |
| Chain of Responsibility | the order is fixed and short; every request must be handled by one known handler |
| Command | no undo, queue, replay, or audit — a direct call is the design |
| Mediator | two or three colleagues; the rules would make it the god object |
| Memento | plain data that a copy already snapshots; only specific operations need undo (Command) |
| Observer | one or two fixed observers; update order carries meaning |
| State | one or two states with simple logic; states share no interface |
| Strategy | one algorithm, fixed; the variants need different interfaces |
| Template Method | the variants differ in sequence, not in steps; composition is simpler |
| Visitor | new element types arrive often; a few operations; plain polymorphism suffices |

## 4. Concept moves

Each is a move, the signal that calls for it, and the counter-rule that blocks it.

**Type-switch → capability.** *Signal:* a chain of "if it is this class" that every new
implementation forces open. *Move:* ask what it can do, not what it is — the knowledge moves
from the caller into the implementation, the only owner of it. Four levels: boolean flags →
capability sets → role interfaces → capability objects. *Counter-rules:* a closed set you own
wants a sealed type and an exhaustive match instead, and a new case *should* break every
call site; many flags on one interface are several types wearing one coat; a flag beside a
method that may throw is a lying flag (a Liskov violation with a runtime apology) — use a
capability object where calling the wrong thing is a bug the type system should catch.

**Scattered construction → composition root.** *Signal:* consumers build their own
collaborators; test setup needs the real thing. *Move:* one place near the entry point
selects and wires concrete parts; consumers receive them. Inject what you would mock
(volatile: I/O, network, clock, randomness); never wrap stable dependencies (standard
library, deterministic helpers). *Counter-rules:* a container referenced outside the root
is a service locator; one implementation that will never vary needs no interface.
Injection is how a dependency arrives; inversion is who owns the contract — passing a
concrete object in is injection without inversion.

**Ad hoc discovery → registry + manifest.** *Signal:* a growing if-chain over component
names, or imports that must change whenever a component is added. *Move:* a registry when
there are more than a handful of interchangeable components (a couple behind one interface
is just DI); a manifest — inert, inspectable data declaring what a component is — when at
least two hold: an open set of components, discovery that must be cheaper than activation,
untrusted components needing a gate, tooling or a catalog, non-programmer authors, or
dependencies between plug-ins. *Counter-rules:* the manifest earns its keep at a trust
boundary; a closed, in-repo set is pure ceremony — import them. Static facts only: a field
whose value depends on runtime state belongs in code, or the config becomes a language with
no debugger. Two sources of truth drift — validate the manifest against the code in CI, or
generate one from the other. The schema is a public API once others author manifests.

**Translation at a seam → port & adapter.** *Signal:* the core calls a technology directly;
testing the core needs the real database. *Move:* the core owns the port, named after its
need in its own vocabulary ("task repository", not "database client"); adapters outside the
core translate to one technology each; the composition root is the only place that knows
both sides. *Counter-rules:* no technology types in a port's signature or the seam leaks;
one adapter is a hypothetical seam — a port earns its interface when a real adapter and a
test double both implement it; no ports in front of stable dependencies.

## 5. Traps

- A language `@decorator` wraps a function or class **once, at definition**. The GoF
  Decorator wraps an **object at runtime**, differently per use. Not the same move.
- An event bus removes the hub but not the rules. Give the coordination a named home, or it
  scatters into subscriptions and nobody can read the workflow.
- A shared instance is not a ban on a second one. Tests need the plain class.
- Injection is how a dependency arrives; inversion is who owns the contract.
- Exhaustiveness is real only where the language checks it (sealed types, closed unions, an
  explicit never-check). A switch over an open enum is not exhaustive.
- A class named `FooStrategy` or `BarFactory` is not evidence of the pattern. Judge the
  shape — what varies, who owns the knowledge — not the suffix.
- Visitor, Composite, State, and capability flags all sit on the **expression problem**:
  cheap new operations *or* cheap new types, never both. Say on the card which side the
  code is on and which side the move optimizes.
