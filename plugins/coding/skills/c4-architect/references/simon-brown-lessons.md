# Simon Brown's Seven Lessons — Operational Form

This reference distils the practical lessons from Simon Brown's talks on the C4 model into seven rules, each in the form **Rule → Why → Applied**. The `c4-architect` skill uses these as hard rules during diagram emission. Quote from this file when a user asks *why* the skill is refusing a particular shape or label.

---

## Rule 1 — A common set of abstractions matters more than a common notation

**Why.** Teams benefit more from sharing the same *mental model* than from forcing everyone to use the same diagramming style or syntax. If everyone agrees on what "Container" and "Component" mean, communication stays aligned even when individual diagrams differ in style. If those abstractions are fuzzy, the prettiest diagram in the world won't rescue the conversation.

**Applied.** The skill starts every session by anchoring on the four C4 abstractions — Person, Software System, Container, Component — in the user's own domain terms, *before* picking any shapes, colours, or tools. Notation is treated as a presentation detail, chosen last.

---

## Rule 2 — Use layered architectural views. Overview first, zoom next, details on demand

**Why.** Architecture communication should be progressive. Different audiences need different levels of detail; executives and users usually need context before internals, whereas developers need to drill down without being flooded too early. Producing all levels at once ignores who the audience is.

**Applied.** The skill runs strict phase gates (Phase 0 → 1 → 2 → 3) and refuses to batch-produce all four levels in one go. After each phase it emits an explicit `STOP.` and waits for the user to confirm or redirect. A diagram that is "right" at the wrong level is still wrong.

---

## Rule 3 — Static structure is the foundation for other views

**Why.** A clear model of the system's *static structure* forms the base for every other view — dynamic / runtime, workflow, deployment, infrastructure, data. Before modelling behaviour or topology, the building blocks themselves must be named and bounded. Dynamic diagrams without a static foundation are just ad-hoc sequence drawings; deployment diagrams without a container model confuse "what runs" with "where it runs".

**Applied.** The skill produces static views first (C1 → C2 → C3) and only *then* offers supplementary diagrams (Dynamic, Deployment, Data). Supplementary views re-use the same boxes and names from the static model to keep the whole set consistent.

---

## Rule 4 — Describe the intent of relationships, not just the connectivity

**Why.** Arrows in architecture diagrams are the single most common failure mode. Labels like `uses`, `calls`, or `makes API calls via` are effectively unlabelled — they carry no information that the mere presence of the arrow didn't already carry. Good labels describe *what actually happens* between two elements: direction, responsibility, and interaction style.

**Applied.** The skill refuses to emit an arrow with a generic verb. Before drawing any arrow, it asks: *"What does A want from B, or what does A give to B?"* Accepted labels are specific: `publishes events to`, `requests customer profile from`, `authenticates via`, `stores files in`, `submits commands to`, `reads pricing from`. If the user can't articulate the intent, that is itself useful information — it often means the design isn't crisp yet.

---

## Rule 5 — Show both directions when the intents differ

**Why.** Two elements that interact both ways often interact asymmetrically — the content, protocol, and meaning of each direction may be completely different. Collapsing such interactions into a single double-headed arrow or one generic label erases the asymmetry and hides responsibilities.

**Applied.** When the user describes a bidirectional interaction, the skill asks: *"Does B return exactly the inverse of what A asks, or does it send something different?"* If the intents differ, it draws **two separate arrows** with distinct labels (e.g., `A ──submits order to──▶ B` and `B ──sends order-status updates to──▶ A`). If the intents are genuinely symmetric (e.g., a simple request/response), one arrow with a request-style label is fine.

---

## Rule 6 — Beware of diagrams that hide the true story behind middleware

**Why.** An infrastructure-centric diagram can obscure the real business relationships. When every service connects to Kafka and nothing else, readers learn the transport technology but miss who is really communicating with whom. The architecture diagram becomes a picture of the plumbing, not the system.

**Applied.** When the user mentions a message broker, event bus, or shared middleware (Kafka, RabbitMQ, SQS, EventBridge, Redis Pub/Sub, NATS, any topic/queue/stream-based transport), the skill does **not** draw the broker as the central hub. It treats the broker as supporting context, and draws the arrow from the *real producer* to the *real consumer*, with the transport detail in parentheses on the arrow label.

---

## Rule 7 — Model the logical interaction; keep middleware as supporting context

**Why.** The improved alternative to Rule 6 still acknowledges the middleware — it doesn't pretend the broker doesn't exist — but it expresses the meaningful logical interaction first. This preserves business intent while staying technically truthful. Readers can see both *what* is being communicated and *how*.

**Applied.** The skill's arrow-label format for middleware-mediated interactions is:

> `<Producer> ──<intent verb> <message type> to──▶ <Consumer> (via <broker> <topic/queue/exchange> <name>)`

Examples:

- `Orders Service ──publishes order-placed events to──▶ Fulfilment Service (via Kafka topic orders.placed)`
- `Billing Service ──sends invoice-reminder commands to──▶ Notification Service (via RabbitMQ queue billing.reminders)`
- `IoT Device ──streams sensor readings to──▶ Analytics Service (via AWS Kinesis stream telemetry)`

The broker appears in the prose of the label, not as a box everything points at.

---

## When a user pushes back

If a user asks why the skill won't draw something (e.g., "just label the arrow 'uses' and move on"), quote the relevant rule from this file and offer a concrete alternative. Most pushback is cost-driven ("it's faster"), and the skill's answer is that the cost is paid later by readers, not by the diagrammer — and that investing five more seconds in an accurate verb is almost always worth it.

If the user overrides a rule deliberately (e.g., they want a middleware-hub diagram for a specific infrastructure-focused audience), comply — the rules are *defaults that serve communication*, not laws. But note the override in the open-questions section so it isn't forgotten.
