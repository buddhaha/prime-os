"""
Seed script — populates ~/PRIME with real project data.

Always wipes the workspace first, so it's safe to run multiple times.

    python -m backend.seed
    docker-compose run seed
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import settings
from backend.services.file_store import FileStore
from backend.models.project import (
    ProjectCreate, ProjectStatus, ProjectType,
    DecisionCreate, DecisionType,
    Alternative, TodoCreate, Priority, TodoUpdate, TodoStatus,
)
from backend.models.resource import ResourceCreate, ResourceType, EdgeCreate, RelationType
from backend.models.agent import AgentCreate, AgentRole, AgentTool


def seed():
    workspace = settings.workspace_path

    # Wipe contents so re-runs are always clean.
    # We clear children rather than the directory itself because the
    # workspace root may be a Docker bind-mount point (can't be deleted).
    if workspace.exists():
        for child in workspace.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        workspace.mkdir(parents=True)

    store = FileStore(workspace)
    print(f"Seeding workspace at: {workspace}")

    # ── Projects ──────────────────────────────────────────────────────

    soc = store.create_project(ProjectCreate(
        name="Autonomous SOC",
        emoji="🛡️",
        description=(
            "Capability build: AI-driven autonomous Security Operations Centre "
            "using WatsonX Orchestrate (or alternative agentic platform). "
            "Goal: automate Tier-1 alert triage, enrichment, and response — "
            "reducing analyst fatigue and mean-time-to-respond."
        ),
        color="#ef4444",
        status=ProjectStatus.active,
        project_type=ProjectType.capability,
        tags=["ibm", "security", "ai", "agentic", "watsonx", "soc"],
    ))
    print(f"  Created project: {soc.id}")

    prime = store.create_project(ProjectCreate(
        name="PRIME OS",
        emoji="🤖",
        description=(
            "Personal intelligence system. Jarvis-style dashboard for managing "
            "projects, knowledge, and autonomous agents — local-first, runs on your machine. "
            "FastAPI backend, file-based storage, D3 knowledge graph, Claude agents."
        ),
        color="#00d4ff",
        status=ProjectStatus.active,
        project_type=ProjectType.personal,
        tags=["software", "ai", "personal", "python", "fastapi"],
    ))
    print(f"  Created project: {prime.id}")

    # ── Decisions — Autonomous SOC ────────────────────────────────────

    store.create_decision(DecisionCreate(
        project_id=soc.id,
        title="Agentic platform: WatsonX Orchestrate vs open alternatives",
        type=DecisionType.adr,
        context=(
            "The capability needs an orchestration layer to coordinate multiple AI agents "
            "(alert triage, enrichment, threat classifier, response). "
            "Key criteria: IBM client trust, enterprise support, speed to demo, "
            "and flexibility to extend beyond security use cases."
        ),
        body=(
            "Evaluate WatsonX Orchestrate as primary platform, with LangGraph and CrewAI "
            "as open alternatives. Decision deferred pending hands-on evaluation of "
            "WatsonX Orchestrate's agent-to-agent handoff and tool-calling capabilities. "
            "If WO cannot handle dynamic multi-agent workflows natively, "
            "fall back to LangGraph with watsonx.ai as the LLM backend."
        ),
        consequences=(
            "WatsonX Orchestrate path: stronger IBM story, pre-built skills marketplace, "
            "but potentially less flexible for custom security workflows. "
            "LangGraph path: full control, open source, but requires more custom build "
            "and weaker IBM narrative for client conversations."
        ),
        alternatives=[
            Alternative(
                title="CrewAI",
                reason="Good for role-based agent teams but limited enterprise support and no IBM integration story.",
            ),
            Alternative(
                title="AutoGen (Microsoft)",
                reason="Strong multi-agent framework but Microsoft-aligned — wrong narrative for IBM pre-sales.",
            ),
            Alternative(
                title="Raw Anthropic/Claude SDK",
                reason="Maximum flexibility but no orchestration primitives — would need to build scheduling and handoff from scratch.",
            ),
        ],
        tags=["architecture", "agentic", "watsonx", "platform"],
    ))

    store.create_decision(DecisionCreate(
        project_id=soc.id,
        title="SOC automation scope: Tier-1 triage first",
        type=DecisionType.decision,
        context=(
            "Full autonomous SOC is a multi-year roadmap. For the capability demo, "
            "scope must be narrow enough to build in weeks and clear enough to show ROI. "
            "The highest-pain, highest-volume SOC problem is Tier-1 alert triage: "
            "80% of alerts are false positives; analysts spend most of their time "
            "on enrichment that could be automated."
        ),
        body=(
            "Focus the demo on Tier-1 alert triage and enrichment: "
            "ingest alert → enrich with threat intel → classify → "
            "auto-close or route to Tier-2 with a structured investigation brief. "
            "Response automation (blocking IPs, isolating endpoints) deferred to Phase 2."
        ),
        consequences=(
            "Faster demo build. Clear, measurable ROI story (alert volume handled, analyst hours saved). "
            "Leaves room to expand to response automation in follow-on conversations. "
            "Risk: client may ask about full response — need a clear Phase 2 roadmap answer."
        ),
        alternatives=[
            Alternative(
                title="Full autonomous response",
                reason="Too broad for a demo; automated response requires deep client-specific SOAR integration.",
            ),
            Alternative(
                title="Threat hunting use case",
                reason="Higher value but harder to demo without client data; Tier-1 triage has a clearer, universal story.",
            ),
        ],
        tags=["scope", "demo", "architecture"],
    ))

    # ── Decisions — PRIME OS ──────────────────────────────────────────

    store.create_decision(DecisionCreate(
        project_id=prime.id,
        title="Local-first file storage for MVP",
        type=DecisionType.adr,
        context=(
            "Need a storage layer that is fast, private, and doesn't require external services. "
            "The system is personal-scale — one user, hundreds of projects, thousands of resources. "
            "Data must be human-readable and git-trackable."
        ),
        body=(
            "All data stored as Markdown + JSON files in ~/PRIME. "
            "No external database for MVP. FileStore service handles all reads and writes. "
            "PostgreSQL migration planned for Phase 2 when structured querying becomes necessary."
        ),
        consequences=(
            "Human-readable, git-trackable, zero infrastructure dependency. "
            "Queries are filesystem scans — acceptable at personal scale. "
            "Will need migration to PostgreSQL before adding multi-device sync or heavy filtering."
        ),
        alternatives=[
            Alternative(title="PostgreSQL from day one", reason="Overkill for personal scale; adds infrastructure before UX is validated."),
            Alternative(title="SQLite", reason="Better than Postgres for local but schema migrations are friction; plain files are simpler to inspect and edit."),
        ],
        tags=["storage", "architecture", "local-first"],
    ))

    store.create_decision(DecisionCreate(
        project_id=prime.id,
        title="Python/FastAPI backend",
        type=DecisionType.adr,
        context=(
            "Need a backend that can run Claude agent loops async, serve a REST API, "
            "and handle WebSocket streams for real-time agent events. "
            "Must be comfortable to extend and not require a build step."
        ),
        body=(
            "FastAPI with asyncio. Runs uvicorn locally. Pydantic v2 for all data models. "
            "Async-first throughout so agent runs don't block API responses."
        ),
        consequences=(
            "Excellent async story for agent loops. Pydantic validation is free. "
            "Auto-generated OpenAPI docs. Python means easy access to ML/AI libraries later. "
            "Not the fastest runtime, but personal-scale traffic makes this irrelevant."
        ),
        alternatives=[
            Alternative(title="Node/Express", reason="Worse async story for long-running agent tasks; smaller ML ecosystem."),
            Alternative(title="Go", reason="Great performance but slower to iterate; no AI/ML library ecosystem."),
        ],
        tags=["backend", "architecture", "python"],
    ))

    store.create_decision(DecisionCreate(
        project_id=prime.id,
        title="HTML prototype before framework commitment",
        type=DecisionType.adr,
        context=(
            "Need to validate all five views and the interaction model before committing "
            "to a frontend framework and build toolchain."
        ),
        body=(
            "Build a rich single-file HTML prototype (prime-os.html) with D3 for the knowledge graph. "
            "Wire to live API once backend is stable. Framework decision (React/Svelte) deferred "
            "until UX is validated and pain points with the HTML prototype are clear."
        ),
        consequences=(
            "Fast iteration, zero build tooling. "
            "Tech stack decision deferred — may never need a framework at this scale. "
            "D3 knowledge graph already working; migrating to a component framework later is manageable."
        ),
        alternatives=[
            Alternative(title="React SPA from the start", reason="Adds build tooling before UX is validated."),
            Alternative(title="Figma mockup", reason="Not interactive enough to evaluate real feel of data-heavy views."),
        ],
        tags=["frontend", "prototype", "architecture"],
    ))

    # ── Todos — Autonomous SOC ────────────────────────────────────────

    for text, prio, section in [
        ("Hands-on evaluation: WatsonX Orchestrate agent-to-agent handoff", Priority.high, "In Progress"),
        ("Map Tier-1 triage workflow to agent action sequence", Priority.high, "In Progress"),
        ("Research QRadar SOAR → WatsonX integration options", Priority.high, "Up Next"),
        ("Build alert triage proof-of-concept (synthetic alerts)", Priority.high, "Up Next"),
        ("Document ROI model: alert volume, analyst hours saved, MTTR reduction", Priority.medium, "Up Next"),
        ("Survey MITRE ATT&CK scenarios suitable for autonomous response", Priority.medium, "Backlog"),
        ("Design integration architecture: SIEM → agents → SOAR", Priority.medium, "Backlog"),
        ("Create client-facing capability deck", Priority.medium, "Backlog"),
        ("Identify 2–3 reference clients for early validation", Priority.low, "Backlog"),
    ]:
        store.create_todo(soc.id, TodoCreate(text=text, priority=prio, section=section))

    # ── Todos — PRIME OS ──────────────────────────────────────────────

    for text, prio, section, done in [
        ("Design data models (Pydantic)", Priority.high, "Done", True),
        ("Build FileStore, GraphEngine, AgentRuntime services", Priority.high, "Done", True),
        ("FastAPI routers + WebSocket agent stream", Priority.high, "Done", True),
        ("Interactive HTML prototype — all 5 views", Priority.high, "Done", True),
        ("Wire prime-os.html to live FastAPI backend", Priority.high, "In Progress", False),
        ("Confirm knowledge graph renders with real data", Priority.high, "In Progress", False),
        ("Docker Compose: postgres + backend services", Priority.high, "Up Next", False),
        ("SQLAlchemy async models + Alembic migrations", Priority.high, "Up Next", False),
        ("LiteLLM abstraction layer (Claude → Ollama → vLLM)", Priority.medium, "Up Next", False),
        ("AgentRunner Protocol — swappable agent frameworks", Priority.medium, "Backlog", False),
        ("News aggregation view (RSS + X feed)", Priority.medium, "Backlog", False),
        ("IBM pre-sales RAG view (doc ingestion + pgvector)", Priority.medium, "Backlog", False),
        ("Langfuse observability sidecar", Priority.low, "Backlog", False),
        ("Voice interface (Web Speech → faster-whisper)", Priority.low, "Backlog", False),
    ]:
        t = store.create_todo(prime.id, TodoCreate(text=text, priority=prio, section=section))
        if done:
            store.update_todo(prime.id, t.id, TodoUpdate(status=TodoStatus.done))

    # ── Concepts — Autonomous SOC ─────────────────────────────────────

    store.create_concept(soc.id, "Alert fatigue",
        "SOC analysts overwhelmed by alert volume — majority are false positives. "
        "The core problem autonomous SOC solves.")
    store.create_concept(soc.id, "Tier-1 triage",
        "First-pass alert investigation: enrich, classify, escalate or auto-close. "
        "Highest volume, most automatable SOC task.")
    store.create_concept(soc.id, "Agentic SOC",
        "Multiple AI agents handling distinct investigation tasks — enrichment, "
        "classification, response — coordinated by an orchestration layer.")
    store.create_concept(soc.id, "MITRE ATT&CK",
        "Framework classifying adversary tactics and techniques. "
        "Used to map alert types to automated response playbooks.")
    store.create_concept(soc.id, "MTTR",
        "Mean Time to Respond — primary KPI for SOC automation ROI. "
        "Autonomous triage can reduce MTTR from hours to minutes for Tier-1 alerts.")

    # ── Concepts — PRIME OS ───────────────────────────────────────────

    store.create_concept(prime.id, "Local-first",
        "Data lives in files on your machine. No cloud dependency, no lock-in, git-trackable.")
    store.create_concept(prime.id, "Knowledge graph",
        "Entities (projects, resources, decisions) linked by semantic edges. "
        "Visualised with D3 force simulation.")
    store.create_concept(prime.id, "Decision archaeology",
        "Every significant choice recorded with context, alternatives, and consequences. "
        "Queryable years later.")
    store.create_concept(prime.id, "AgentRunner Protocol",
        "Thin Python Protocol interface over agent frameworks — swapping Claude for "
        "Ollama or LangGraph requires only a config change.")

    # ── Resources — Autonomous SOC ────────────────────────────────────

    soc_r1 = store.create_resource(ResourceCreate(
        type=ResourceType.article,
        title="The Case for Autonomous Security Operations",
        description="Overview of how agentic AI changes the SOC model — from reactive to autonomous. Key framing for client conversations.",
        project_ids=[soc.id],
        tags=["soc", "autonomous", "ai", "framing"],
    ))
    soc_r2 = store.create_resource(ResourceCreate(
        type=ResourceType.article,
        title="WatsonX Orchestrate: Enterprise Agentic Workflows",
        description="IBM's documentation and positioning for WatsonX Orchestrate — agent skills, tool integration, multi-agent coordination.",
        source_url="https://www.ibm.com/products/watsonx-orchestrate",
        project_ids=[soc.id],
        tags=["watsonx", "orchestrate", "ibm", "agentic"],
    ))
    soc_r3 = store.create_resource(ResourceCreate(
        type=ResourceType.article,
        title="LangGraph vs WatsonX Orchestrate for Security Automation",
        description="Technical comparison of LangGraph's state machine model vs WatsonX Orchestrate's skill-based approach for multi-agent security workflows.",
        project_ids=[soc.id],
        tags=["langgraph", "watsonx", "comparison", "agentic"],
    ))
    soc_n1 = store.create_resource(ResourceCreate(
        type=ResourceType.note,
        title="SOC Demo Architecture — Initial Thoughts",
        description="Working notes on the demo flow: synthetic alert ingestion → enrichment agent → classifier → analyst brief output.",
        project_ids=[soc.id],
        tags=["architecture", "demo", "design"],
        content=(
            "# SOC Demo Architecture\n\n"
            "## Demo flow\n"
            "1. Ingest synthetic SIEM alert (JSON payload simulating QRadar offense)\n"
            "2. **Enrichment agent** — queries threat intel (VirusTotal, AbuseIPDB) for IPs/domains\n"
            "3. **Classifier agent** — scores alert: true positive / false positive / needs escalation\n"
            "4. **Brief writer** — produces structured investigation summary for Tier-2 analyst\n"
            "5. Auto-close false positives; route true positives to ticketing\n\n"
            "## Open questions\n"
            "- WatsonX Orchestrate: can agents call external APIs natively via skills?\n"
            "- How to handle agent-to-agent handoff state? Does WO have shared context?\n"
            "- QRadar SOAR integration: webhook-based or REST polling?\n\n"
            "## Tools agents need\n"
            "- `query_threat_intel(ip, domain)` → enrichment data\n"
            "- `get_alert_details(alert_id)` → full alert from SIEM\n"
            "- `classify_alert(enriched_data)` → verdict + confidence\n"
            "- `create_investigation_brief(alert, enrichment, verdict)` → Markdown brief\n"
            "- `close_alert(alert_id, reason)` → write back to SIEM/SOAR\n"
        ),
    ))
    soc_n2 = store.create_resource(ResourceCreate(
        type=ResourceType.note,
        title="WatsonX Orchestrate Evaluation Checklist",
        description="What to test during hands-on WatsonX Orchestrate evaluation — agent chaining, external APIs, latency, error handling.",
        project_ids=[soc.id],
        tags=["watsonx", "evaluation", "checklist"],
        content=(
            "# WatsonX Orchestrate Evaluation\n\n"
            "## What to test\n"
            "- [ ] Create a custom skill that calls an external REST API\n"
            "- [ ] Chain two agents: enrichment → classifier\n"
            "- [ ] Inspect shared context between agent invocations\n"
            "- [ ] Latency: how long does a 3-agent chain take end-to-end?\n"
            "- [ ] Error handling: what happens when a skill fails mid-chain?\n"
            "- [ ] Can agents write structured output (JSON) vs free text?\n\n"
            "## Notes\n"
            "*(to be filled during evaluation)*\n"
        ),
    ))
    soc_a1 = store.create_resource(ResourceCreate(
        type=ResourceType.artifact,
        title="Autonomous SOC Capability Deck v0.1",
        description="Client-facing presentation: problem statement, solution architecture, demo flow, ROI model.",
        project_ids=[soc.id],
        tags=["presentation", "client", "capability"],
    ))

    # ── Resources — PRIME OS ──────────────────────────────────────────

    prime_r1 = store.create_resource(ResourceCreate(
        type=ResourceType.article,
        title="Building a Second Brain — Tiago Forte",
        description="Framework for externalising knowledge into a trusted system. Core inspiration for PRIME's knowledge model.",
        source_url="https://www.buildingasecondbrain.com",
        project_ids=[prime.id],
        tags=["knowledge-management", "pkm", "inspiration"],
        content=(
            "# Building a Second Brain\n\n"
            "Core idea: offload knowledge from your head into a trusted external system. "
            "Capture → Organise → Distil → Express.\n\n"
            "**Relevance to PRIME:** The knowledge graph + resource system is PRIME's "
            "implementation of this — with agents that actively build and connect the graph."
        ),
    ))
    prime_r2 = store.create_resource(ResourceCreate(
        type=ResourceType.article,
        title="Local-first Software — Kleppmann et al.",
        description="Academic case for keeping data on user devices with sync as a feature, not a requirement. Underpins PRIME's file-first architecture.",
        source_url="https://www.inkandswitch.com/local-first/",
        project_ids=[prime.id],
        tags=["local-first", "architecture", "data"],
    ))
    prime_n1 = store.create_resource(ResourceCreate(
        type=ResourceType.note,
        title="Phase 1 API Wiring — Plan",
        description="What needs to change in prime-os.html to call the live FastAPI backend instead of returning hardcoded data.",
        project_ids=[prime.id],
        tags=["frontend", "api", "plan"],
        content=(
            "# Frontend API Wiring Plan\n\n"
            "## Endpoints to wire\n"
            "| View | Current | Target |\n"
            "|------|---------|--------|\n"
            "| Projects | Hardcoded JS array | `GET /api/projects` |\n"
            "| Project detail | Hardcoded | `GET /api/projects/{id}` |\n"
            "| Knowledge graph | Hardcoded nodes/edges | `GET /api/graph` |\n"
            "| Agents | Hardcoded cards | `GET /api/agents` |\n"
            "| Agent runs | Static log | `WS /api/agents/ws` |\n\n"
            "## Loading states\n"
            "Each view needs a spinner while data loads. "
            "Graph needs to handle empty state gracefully.\n\n"
            "## Error handling\n"
            "If backend is not running, show a 'Backend offline' banner "
            "rather than a broken UI.\n"
        ),
    ))
    prime_n2 = store.create_resource(ResourceCreate(
        type=ResourceType.note,
        title="PRIME OS Roadmap",
        description="Prioritised development sequence — what to build in what order and why.",
        project_ids=[prime.id],
        tags=["roadmap", "planning"],
        content=(
            "# PRIME OS Roadmap\n\n"
            "## Phase 1 — Make it run (current)\n"
            "Wire frontend to live API. Confirm knowledge graph renders with real data.\n\n"
            "## Phase 2 — Docker + PostgreSQL\n"
            "docker-compose.yml, SQLAlchemy async models, Alembic migrations.\n\n"
            "## Phase 3 — LiteLLM + real agents\n"
            "Replace hardcoded Anthropic SDK with LiteLLM. AgentRunner Protocol. "
            "Agents actually do work.\n\n"
            "## Phase 4 — News view\n"
            "RSS aggregation, curated AI/tech sources, background polling task.\n\n"
            "## Phase 5 — IBM pre-sales RAG\n"
            "Document ingestion (URL + PDF), pgvector, RAG query endpoint.\n\n"
            "## Phase 6 — Advanced\n"
            "Langfuse, voice interface, multi-agent orchestration.\n"
        ),
    ))
    prime_a1 = store.create_resource(ResourceCreate(
        type=ResourceType.artifact,
        title="PRIME Architecture Diagram",
        description="System diagram: frontend ↔ FastAPI ↔ FileStore + GraphEngine + AgentRuntime ↔ Claude API.",
        project_ids=[prime.id],
        tags=["architecture", "design"],
    ))

    # ── Edges ─────────────────────────────────────────────────────────

    store.create_edge(EdgeCreate(
        from_id=soc_n1.id, to_id=soc_r2.id,
        relation=RelationType.references,
        note="Demo architecture depends on WatsonX Orchestrate capabilities",
    ))
    store.create_edge(EdgeCreate(
        from_id=soc_n2.id, to_id=soc_r3.id,
        relation=RelationType.references,
        note="Evaluation checklist informed by LangGraph vs WatsonX comparison",
    ))
    store.create_edge(EdgeCreate(
        from_id=soc_a1.id, to_id=soc_r1.id,
        relation=RelationType.cites,
        note="Capability deck opens with the autonomous SOC framing article",
    ))
    store.create_edge(EdgeCreate(
        from_id=prime_n2.id, to_id=prime_n1.id,
        relation=RelationType.references,
        note="Roadmap Phase 1 details are in the API wiring plan note",
    ))
    store.create_edge(EdgeCreate(
        from_id=prime_a1.id, to_id=prime_r2.id,
        relation=RelationType.cites,
        note="Architecture decisions grounded in local-first software principles",
    ))

    # ── Agents ────────────────────────────────────────────────────────

    store.create_agent(AgentCreate(
        name="Research", role=AgentRole.research, emoji="🔍",
        description="Gathers information, synthesises sources, saves structured research briefs to the knowledge base.",
        tools=[
            AgentTool.web_search, AgentTool.write_resource, AgentTool.read_resource,
            AgentTool.create_note, AgentTool.link_resources, AgentTool.list_projects,
        ],
    ))
    store.create_agent(AgentCreate(
        name="Writer", role=AgentRole.writer, emoji="✍️",
        description="Writes ADRs, capability briefs, summaries, and LinkedIn posts. Reads existing resources before writing.",
        tools=[
            AgentTool.read_resource, AgentTool.write_resource, AgentTool.create_decision,
            AgentTool.read_project, AgentTool.list_projects,
        ],
    ))
    store.create_agent(AgentCreate(
        name="Analyst", role=AgentRole.analyst, emoji="📊",
        description="Analyses data, compares options, produces structured reports with clear recommendations.",
        tools=[
            AgentTool.read_resource, AgentTool.write_resource,
            AgentTool.read_project, AgentTool.create_note,
        ],
    ))
    store.create_agent(AgentCreate(
        name="Monitor", role=AgentRole.monitor, emoji="👁️",
        description="Watches sources and surfaces only what's relevant — new releases, competitive moves, research worth reading.",
        tools=[AgentTool.web_search, AgentTool.create_note, AgentTool.read_project],
    ))

    print("\n✅ Seed complete.")
    print(f"   Projects: Autonomous SOC (capability), PRIME OS (personal)")
    print(f"   Resources: 6 SOC + 5 PRIME = 11 total")
    print(f"   Agents: Research, Writer, Analyst, Monitor")
    print(f"\nStart the server:")
    print(f"   uvicorn backend.main:app --host 127.0.0.1 --port 7474 --reload")


if __name__ == "__main__":
    seed()
