# DDD Strategic Design — A Plain-English Primer

This is a short, practical reference for the subset of **Domain-Driven Design (DDD)** that the `c4-architect` skill uses while producing C4 diagrams. It covers **Strategic Design** only — the high-level concepts that help you *find the boundaries* in a system. It does not cover tactical DDD (entities, value objects, aggregates, repositories) — those live at the class-and-code level, below C4's scope for this skill.

Read this file when:

- A user asks "what do you mean by bounded context?"
- The skill needs to justify why it's drawing context boundaries a particular way.
- You are teaching a user who is unfamiliar with DDD and wants to go one step deeper than the one-line glosses in `SKILL.md`.

---

## What "Strategic Design" means

DDD splits into two halves:

| Half | What it's about | Scope for this skill |
|---|---|---|
| **Strategic Design** | Where to draw boundaries. What to build, what to buy, what to treat as legacy. How separate teams relate. | **In scope.** |
| **Tactical Design** | How to structure classes inside one bounded context. Aggregates, entities, value objects, domain events, repositories. | **Out of scope** for C4 — defer to code-level design skills. |

The `c4-architect` skill lives firmly in the strategic half. Every concept in this primer is about **finding seams**, not about implementing them.

---

## 1. Bounded Context — the load-bearing idea

**One-line gloss:** *A region of the system where each domain term has one specific, agreed meaning.*

### Plain-English explanation

In any non-trivial system, the same word means different things in different parts of the business. Consider an e-commerce company:

| Word | In Sales & Ordering | In Warehouse & Shipping | In Billing & Accounting |
|---|---|---|---|
| `Order` | A shopping cart with payment committed | A pick-list with a dispatch deadline | A line-item on an invoice awaiting payment |
| `Customer` | A person with a cart, shipping address, and preferences | A delivery destination with a signature requirement | A debtor with a credit history and tax ID |
| `Product` | A sellable SKU with photos, pricing, reviews | A physical item with weight, dimensions, and a shelf location | A general-ledger account for revenue recognition |

These aren't *wrong* definitions. They're each *correct for their own area*. Trying to force all three teams to share a single `Customer` class either:

1. Produces a God-object that grows without bound ("`Customer.creditLimit` is only used by Accounting, but now every service has to deal with it"), or
2. Produces endless meetings where teams negotiate whose definition is "the real one".

A **bounded context** is the explicit acknowledgement that *this region of the system uses `Customer` to mean this specific thing*, and we're OK with a different region using `Customer` differently. Boundaries are a feature, not a bug.

### How to find bounded contexts in practice

Listen for:

- **Different stakeholders using the same word differently.** ("Sales calls that a 'customer', but Support calls the same thing a 'ticket-owner'.")
- **Natural organisational seams.** (Different teams, different departments, different domain experts.)
- **Places where translation happens.** (Data moves from system A to system B and somebody *maps fields*. That mapping is a context boundary in disguise.)
- **Subtle definitional disagreements.** (Meeting ends with "oh, you meant X — we were talking about Y".)

### How bounded contexts relate to C4

A bounded context often maps to **one C4 container**, or to a **group of containers** that share a model. It is *not* the same thing as a microservice — a bounded context is about *model coherence*, a container is about *deployability*. Most of the time they line up; sometimes one bounded context spans multiple containers (e.g., a web app plus its API plus its database all serve the Ordering context).

In C4 Level 2 diagrams, the skill groups containers into dashed boxes labelled with their bounded-context name, so the domain seams and the deployment seams are both visible.

---

## 2. Ubiquitous Language — the vocabulary inside one context

**One-line gloss:** *The single agreed vocabulary used inside one bounded context, by code, docs, and conversation alike.*

### Plain-English explanation

Inside a single bounded context, one word means one thing, and *everyone uses that word*. The developers' class names, the domain experts' conversations, the database columns, the API endpoints, and the requirements document all use the same vocabulary. If the domain expert says "order", the code says `Order`, not `PurchaseRequest` or `Transaction` or `Booking`.

This sounds obvious. It's almost never done in practice.

### Why it matters

When vocabulary drifts, translation overhead grows. Developers translate from business-speak to code-speak and back again every time they talk to a domain expert. Bugs creep in at the translation seams. The ubiquitous language rule says: *don't translate, share*. Force the business terms into the code, even when they're ugly ("`Provisional Admission Encounter`" is fine if that's what hospital admissions staff call it).

### Connection to Simon Brown's Lesson 1

Brown says "common abstractions matter more than common notation". Ubiquitous Language is the same principle one level below — *common vocabulary matters more than clever naming*. Both rules say: agree on *what things are called*, then worry about how to draw them.

### Applied by the skill

When the skill produces a container or component table, it uses the user's **own words** from the intake, not generic labels like "UserService" or "OrderManager". If the user's domain calls them "Appointments" rather than "Bookings", the diagram says `Appointments`.

---

## 3. Subdomain triage — Core / Supporting / Generic

**One-line gloss (each):**

- **Core domain** — the part that is your business's competitive advantage.
- **Supporting subdomain** — necessary for your business to function, but not differentiating.
- **Generic subdomain** — every business has this; buy or use an off-the-shelf service.

### Plain-English explanation

Not all parts of your system deserve equal investment. A triage:

| Type | What it is | How to treat it |
|---|---|---|
| **Core** | The thing you do better than competitors. If you outsourced this, you'd lose your reason to exist. | Build with care. Best engineers. Best tests. Most domain expertise. |
| **Supporting** | You need it, but it's not where you win. Most businesses in your industry have something similar. | Build simply. Don't over-engineer. Revisit later if it grows strategic. |
| **Generic** | Every business has this: authentication, email delivery, payment processing, invoicing, user management. | Buy. Use Auth0, Stripe, SendGrid, QuickBooks. Do not build. |

### Example — hypothetical telehealth platform

| Subdomain | Type | Reasoning |
|---|---|---|
| Clinical consultation workflow (the actual doctor-patient video session, diagnostic tooling, medical record) | Core | This is the product. |
| Scheduling & availability | Supporting | Every booking app has this; it's important but doesn't differentiate. |
| Patient identity & login | Generic | Use Auth0 / Cognito / Keycloak. |
| Payment / billing | Generic | Use Stripe. |
| SMS / push notifications | Generic | Use Twilio / Firebase. |
| Clinician-AI second-opinion engine | Core | Differentiator. Competitive moat. |
| Document storage | Generic | Use S3. |
| Compliance / audit log | Supporting | Must exist for regulatory reasons, but off-the-shelf solutions exist. |

### How the skill uses it

At C1 (System Context), when the user's description shows multiple distinguishable areas, the skill offers a brief triage. This often changes the C2 decision: Generic subdomains may become *external systems* rather than first-class containers inside your boundary (because you'll buy them). Core subdomains may deserve their own containers with more internal structure.

---

## 4. Context Map — how bounded contexts relate

**One-line gloss:** *The picture of how your bounded contexts relate to each other — which depends on which, and how.*

A context map is just a diagram of bounded contexts with labelled arrows between them. Evans catalogued seven recurring **patterns of relationship** between contexts. These are not mutually exclusive — a pair of contexts can have multiple relationships. The skill names the relationship type when drawing arrows between contexts at C2, because the *type* communicates more than the arrow itself.

Each pattern below has: a plain-English recognition phrase, when it fits, and what the arrow label typically looks like.

### 4.1 Customer / Supplier

**One-line gloss:** *Downstream (customer) needs upstream (supplier); upstream accommodates, with some roadmap influence flowing back.*

**Recognise it when:** "Team A needs something from Team B, but Team B is willing to prioritise A's needs because A is a legitimate customer. They negotiate, they plan together."

**Typical arrow:** `Fulfilment ──requests order details from──▶ Orders   (Customer/Supplier)`

This is the *healthy default* between two teams inside the same company.

### 4.2 Shared Kernel

**One-line gloss:** *Two contexts share a small common model; any change requires agreement from both sides.*

**Recognise it when:** "We have a small set of types that both services use — if we want to change them, we have to update both at once."

**Typical arrow:** A dashed box spanning both contexts, labelled `Shared Kernel: Money, Currency, Address`.

**Warning:** Shared kernels ossify quickly. Keep them tiny. If the shared model grows beyond a few types, split it — it's probably becoming its own context.

### 4.3 Conformist

**One-line gloss:** *Downstream accepts upstream's model as-is, no translation.*

**Recognise it when:** "We just use their data the way it arrives. We named our fields to match theirs."

**Typical arrow:** `Reporting ──conforms to──▶ Orders  (Conformist)`

**When it fits:** Upstream is stable and their model is basically fine. Translation would be overhead with no benefit.

**When it doesn't:** Upstream's model is a mess and it's poisoning your codebase.

### 4.4 Anticorruption Layer

**One-line gloss:** *Downstream wraps upstream's model in a translation layer to protect its own.*

**Recognise it when:** "Their API is a mess, but we can't change it. So we built a layer that translates their weird data into our clean domain objects."

**Typical arrow:** `Clinical Records ──translates via anticorruption layer──▶ Legacy EMR`

**When it fits:** Upstream is legacy, third-party, or politically untouchable, AND has a model you actively don't want to adopt. The ACL protects your Core from their mess.

**Cost:** You have to maintain the translation. When their model changes, you update the ACL, not your Core — that's the point, but the work is real.

### 4.5 Open Host Service

**One-line gloss:** *Upstream publishes a well-defined public interface for many consumers.*

**Recognise it when:** "We offer a public API. We don't know all our consumers in advance. We version it carefully."

**Typical arrow:** `Many Consumers ──consume──▶ Identity Service  (Open Host)`

**When it fits:** One context serves many. Rather than negotiating with each consumer, publish a well-documented interface and let consumers come and go.

### 4.6 Published Language

**One-line gloss:** *A shared, documented data format (e.g., a versioned event schema or OpenAPI spec) used for communication.*

**Recognise it when:** "We have a published JSON schema / Avro schema / protobuf / OpenAPI spec that defines the messages. Consumers build against the schema, not our internal types."

Often paired with Open Host Service: *the host publishes a language*, and consumers *conform to the language*, not to the host's internal model.

**Typical annotation:** `Published Language: orders.placed@v3 (Avro schema in schema-registry)`.

### 4.7 Separate Ways

**One-line gloss:** *Deliberate non-integration — two contexts do not talk to each other.*

**Recognise it when:** "Yes, Ops and Marketing both track 'customers', but they never share data. They each query their own source."

**Typical diagram:** No arrow at all, but a note: `Separate Ways — HR Context and Procurement Context do not integrate; any overlap is handled manually.`

**When it fits:** Integration cost exceeds integration value. Common with small, peripheral contexts. Explicitly naming "Separate Ways" is useful because it signals the absence-of-arrow is a *deliberate choice*, not an oversight.

---

## 5. Big Ball of Mud — a context-map anti-pattern

**One-line gloss:** *A region with no clear model boundaries — entanglement to be cleaned up, not modelled.*

Not one of Evans's seven patterns, but worth naming. A Big Ball of Mud is code or a subsystem where the ubiquitous language has collapsed, bounded contexts are unidentifiable, and every change ripples unpredictably.

### How to handle it in a C4 diagram

- **Do not try to model it as a bounded context.** It isn't one.
- **Draw a dashed box around it and label it `Legacy / Big Ball of Mud — pending decomposition`.**
- **Use an Anticorruption Layer** between the mud and anything you care about, to keep the mud from infecting cleaner contexts.
- **Flag it in the open-questions list** as something that needs its own refactoring plan.

Most systems of any age contain at least one Big Ball of Mud. Naming it honestly beats pretending it's an integrated bounded context.

---

## 6. Quick reference — which concept answers which question

| User question during C4 work | DDD concept that helps |
|---|---|
| "Where should I draw container boundaries?" | Bounded Context |
| "Why do two services use the same word differently?" | Bounded Context (they're in different ones) |
| "What should we build in-house vs. buy?" | Subdomain triage (Core / Supporting / Generic) |
| "How should these two services talk to each other?" | Context Map patterns |
| "Their API is ugly and I don't want it in my code" | Anticorruption Layer |
| "We offer an API to many consumers" | Open Host Service + Published Language |
| "Two teams share a small common model" | Shared Kernel |
| "Teams A and B both track customers but never integrate" | Separate Ways |
| "This region is a mess and I can't find boundaries" | Big Ball of Mud (anti-pattern) |

---

## 7. Further reading

- **Eric Evans — *Domain-Driven Design: Tackling Complexity in the Heart of Software*** (2003). The original, comprehensive. Strategic Design is the last third.
- **Vaughn Vernon — *Implementing Domain-Driven Design*** (2013). More modern, with concrete code examples.
- **Vaughn Vernon — *Domain-Driven Design Distilled*** (2016). A short (~150 pages) intro — the fastest on-ramp.
- **[dddcommunity.org](https://www.dddcommunity.org/)** — community site with articles and patterns.
- **[github.com/ddd-crew/context-mapping](https://github.com/ddd-crew/context-mapping)** — a visual cheat-sheet of context map patterns.

---

## 8. Guard-rails when teaching DDD to non-DDD users

The `c4-architect` skill should:

- **Never assume the user knows any DDD term.** Always gloss on first use.
- **Use the user's own domain words**, not generic placeholders, whenever possible.
- **Prefer the plain-English recognition phrase over the pattern name.** Say "this is the pattern where your team wraps their ugly API in a translation layer — it's called an Anticorruption Layer" rather than leading with the term.
- **Skip DDD concepts when they wouldn't change the diagram.** A one-container system doesn't need bounded-context vocabulary. Don't teach for teaching's sake.
- **Offer escape hatches.** "If you want, I can skip the DDD framing entirely and just use plain C4 vocabulary — it works, just loses a bit of precision." Respect the user's stated preference.
