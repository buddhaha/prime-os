---
name: grill-me
description: "Interview relentlessly about a plan or design until reaching shared understanding. Walk down every branch of the decision tree, resolving dependencies one at a time. Use when stress-testing a PRIME feature, architecture decision, or implementation approach."
---

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one by one. For each question, provide your recommended answer based on what you know about PRIME's architecture and goals.

Ask questions one at a time.

If a question can be answered by reading the codebase or ARCHITECTURE.md, read it first instead of asking.

Pay particular attention to:
- How this decision interacts with the local-first data model (~/PRIME filesystem)
- Whether this introduces provider lock-in (LLM, database, framework)
- Whether this needs to survive the Claude → Ollama/vLLM migration
- Whether this can be validated in the HTML prototype before building backend infrastructure
