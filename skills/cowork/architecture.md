---
name: architecture
description: "Work through an architecture decision record (ADR) for PRIME. Use when choosing between technologies, evaluating a design trade-off, or documenting a decision that future-you will need to understand."
---

Help me write an Architecture Decision Record for PRIME. Structure it as follows:

**Title** — Short, imperative: "Use X for Y"

**Context** — What problem are we solving? What constraints matter? What does the current state of PRIME impose?

**Decision** — What are we choosing to do?

**Alternatives considered** — For each alternative: what is it, and why did we reject it? Be specific about the rejection reason — not "too complex" but "adds a build step before UX is validated" or "creates external dependency that conflicts with local-first model."

**Consequences** — What does this decision unlock? What does it close off? What will future-Mirek thank us for, and what will he have to live with?

After drafting, challenge the decision: what's the strongest argument for the rejected alternative? Is there a condition under which we'd reverse this decision?

Keep the tone direct. This is a document for one person who needs to remember why they made a call, not a committee report.
