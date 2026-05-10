"""
Seed script — populates the PostgreSQL database with real project data.

    docker-compose run seed          # via Docker
    python -m backend.seed           # locally (needs DATABASE_URL in env / .env)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import create_tables, AsyncSessionLocal
from backend.services.db_store import DBStore
from backend.models.project import (
    ProjectCreate, ProjectStatus, ProjectType,
    DecisionCreate, DecisionType,
    Alternative, TodoCreate, Priority, TodoUpdate, TodoStatus,
    ConceptCreate,
)
from backend.models.resource import ResourceCreate, ResourceType, EdgeCreate, RelationType


async def seed_db(store: DBStore) -> None:
    """Populate the database. Expects an empty DB (called from lifespan or CLI)."""

    print("Seeding database…")

    # ── Projects ──────────────────────────────────────────────────────

    soc = await store.create_project(ProjectCreate(
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

    prime = await store.create_project(ProjectCreate(
        name="PRIME OS",
        emoji="🤖",
        description=(
            "Personal intelligence system. Jarvis-style dashboard for managing "
            "projects, knowledge, and autonomous agents — local-first, runs on your machine. "
            "FastAPI backend, PostgreSQL storage, D3 knowledge graph, Claude agents."
        ),
        color="#00d4ff",
        status=ProjectStatus.active,
        project_type=ProjectType.personal,
        tags=["software", "ai", "personal", "python", "fastapi", "postgres"],
    ))

    print(f"  Projects: {soc.id}, {prime.id}")

    # ── Decisions — Autonomous SOC ────────────────────────────────────

    await store.create_decision(DecisionCreate(
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
            "WatsonX Orchestrate's agent-to-agent handoff and tool-calling capabilities."
        ),
        consequences=(
            "WatsonX Orchestrate path: stronger IBM story, pre-built skills marketplace, "
            "but potentially less flexible for custom security workflows."
        ),
        alternatives=[
            Alternative(title="CrewAI", reason="Good for role-based agent teams but limited enterprise support and no IBM integration story."),
            Alternative(title="AutoGen (Microsoft)", reason="Strong multi-agent framework but Microsoft-aligned — wrong narrative for IBM pre-sales."),
            Alternative(title="Raw Anthropic/Claude SDK", reason="Maximum flexibility but no orchestration primitives — needs hand-built scheduling."),
        ],
    ))

    await store.create_decision(DecisionCreate(
        project_id=soc.id,
        title="SOC automation scope: Tier-1 triage first",
        type=DecisionType.decision,
        context=(
            "Full autonomous SOC is a multi-year roadmap. For the capability demo, "
            "scope must be narrow enough to build in weeks and clear enough to show ROI."
        ),
        body=(
            "Focus the demo on Tier-1 alert triage and enrichment: "
            "ingest alert → enrich with threat intel → classify → "
            "auto-close or route to Tier-2 with a structured investigation brief."
        ),
        consequences=(
            "Faster demo build. Clear, measurable ROI story. "
            "Leaves room to expand to response automation in follow-on conversations."
        ),
        alternatives=[
            Alternative(title="Full autonomous response", reason="Too broad for a demo; requires deep client-specific SOAR integration."),
            Alternative(title="Threat hunting", reason="Higher value but harder to demo without client data."),
        ],
    ))

    # ── Decisions — PRIME OS ──────────────────────────────────────────

    await store.create_decision(DecisionCreate(
        project_id=prime.id,
        title="PostgreSQL replaces file store",
        type=DecisionType.adr,
        context=(
            "File store served MVP well — no infra dependency, human-readable, git-trackable. "
            "Moving to PostgreSQL enables structured queries, filtering, multi-device sync, "
            "and pgvector for RAG (Phase 5). SQLAlchemy async keeps the FastAPI story clean."
        ),
        body=(
            "Replace FileStore with DBStore (SQLAlchemy async + asyncpg). "
            "PostgreSQL 16 added to docker-compose. Alembic for migrations. "
            "Same Pydantic models retained — only the service layer changes."
        ),
        consequences=(
            "Better query performance and filtering at scale. "
            "Enables pgvector for semantic search. Requires Docker for local dev. "
            "File-based human-readable data is lost — compensated by Alembic migration history."
        ),
        alternatives=[
            Alternative(title="SQLite", reason="No Docker dependency but no pgvector, no async driver, poor concurrency."),
            Alternative(title="Keep files + add SQLite index", reason="Hybrid complexity; doesn't solve the pgvector need."),
        ],
    ))

    await store.create_decision(DecisionCreate(
        project_id=prime.id,
        title="Python/FastAPI backend",
        type=DecisionType.adr,
        context="Need a backend that runs Claude agent loops async, serves REST API, and handles WebSocket streams.",
        body="FastAPI with asyncio. Uvicorn. Pydantic v2 for all data models. Async-first throughout.",
        consequences="Excellent async story. Auto-generated OpenAPI docs. Python ML/AI ecosystem access.",
        alternatives=[
            Alternative(title="Node/Express", reason="Worse async story for long-running agent tasks."),
            Alternative(title="Go", reason="Great performance but slower to iterate; no AI/ML ecosystem."),
        ],
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
        await store.create_todo(soc.id, TodoCreate(text=text, priority=prio, section=section))

    # ── Todos — PRIME OS ──────────────────────────────────────────────

    for text, prio, section, done in [
        ("Design data models (Pydantic)", Priority.high, "Done", True),
        ("Build FileStore, GraphEngine, AgentRuntime services", Priority.high, "Done", True),
        ("FastAPI routers + WebSocket agent stream", Priority.high, "Done", True),
        ("Interactive HTML prototype — all 5 views", Priority.high, "Done", True),
        ("Wire prime-os.html to live FastAPI backend", Priority.high, "Done", True),
        ("Docker Compose + PostgreSQL", Priority.high, "Done", True),
        ("SQLAlchemy async models + DBStore", Priority.high, "Done", True),
        ("Alembic migrations setup", Priority.high, "In Progress", False),
        ("LiteLLM abstraction layer (Claude → Ollama → vLLM)", Priority.medium, "Up Next", False),
        ("AgentRunner Protocol — swappable agent frameworks", Priority.medium, "Backlog", False),
        ("News aggregation view (RSS + X feed)", Priority.medium, "Backlog", False),
        ("IBM pre-sales RAG view (doc ingestion + pgvector)", Priority.medium, "Backlog", False),
        ("Langfuse observability sidecar", Priority.low, "Backlog", False),
        ("Voice interface (Web Speech → faster-whisper)", Priority.low, "Backlog", False),
    ]:
        t = await store.create_todo(prime.id, TodoCreate(text=text, priority=prio, section=section))
        if done:
            await store.update_todo(prime.id, t.id, TodoUpdate(status=TodoStatus.done))

    # ── Concepts — Autonomous SOC ─────────────────────────────────────

    for name, desc in [
        ("Alert fatigue", "SOC analysts overwhelmed by alert volume — majority are false positives. The core problem autonomous SOC solves."),
        ("Tier-1 triage", "First-pass alert investigation: enrich, classify, escalate or auto-close. Highest volume, most automatable SOC task."),
        ("Agentic SOC", "Multiple AI agents handling distinct investigation tasks — enrichment, classification, response — coordinated by an orchestration layer."),
        ("MITRE ATT&CK", "Framework classifying adversary tactics and techniques. Used to map alert types to automated response playbooks."),
        ("MTTR", "Mean Time to Respond — primary KPI for SOC automation ROI. Autonomous triage can reduce MTTR from hours to minutes for Tier-1 alerts."),
    ]:
        await store.create_concept(soc.id, ConceptCreate(name=name, desc=desc))

    # ── Concepts — PRIME OS ───────────────────────────────────────────

    for name, desc in [
        ("Local-first", "Data lives on your machine. No cloud dependency, no lock-in, git-trackable."),
        ("Knowledge graph", "Entities (projects, resources, decisions) linked by semantic edges. Visualised with D3 force simulation."),
        ("Decision archaeology", "Every significant choice recorded with context, alternatives, and consequences. Queryable years later."),
        ("AgentRunner Protocol", "Thin Python Protocol interface over agent frameworks — swapping Claude for Ollama or LangGraph requires only a config change."),
    ]:
        await store.create_concept(prime.id, ConceptCreate(name=name, desc=desc))

    # ── Resources — Autonomous SOC ────────────────────────────────────

    soc_r1 = await store.create_resource(ResourceCreate(
        type=ResourceType.article,
        title="The Case for Autonomous Security Operations",
        description="Overview of how agentic AI changes the SOC model — from reactive to autonomous. Key framing for client conversations.",
        project_ids=[soc.id],
        tags=["soc", "autonomous", "ai", "framing"],
    ))
    soc_r2 = await store.create_resource(ResourceCreate(
        type=ResourceType.article,
        title="WatsonX Orchestrate: Enterprise Agentic Workflows",
        description="IBM's documentation and positioning for WatsonX Orchestrate.",
        source_url="https://www.ibm.com/products/watsonx-orchestrate",
        project_ids=[soc.id],
        tags=["watsonx", "orchestrate", "ibm", "agentic"],
    ))
    soc_n1 = await store.create_resource(ResourceCreate(
        type=ResourceType.note,
        title="SOC Demo Architecture — Initial Thoughts",
        description="Working notes on the demo flow: synthetic alert ingestion → enrichment agent → classifier → analyst brief output.",
        project_ids=[soc.id],
        tags=["architecture", "demo", "design"],
        content=(
            "# SOC Demo Architecture\n\n"
            "## Demo flow\n"
            "1. Ingest synthetic SIEM alert (JSON payload simulating QRadar offense)\n"
            "2. Enrichment agent — queries threat intel for IPs/domains\n"
            "3. Classifier agent — scores alert: true positive / false positive / escalate\n"
            "4. Brief writer — produces structured investigation summary\n"
            "5. Auto-close false positives; route true positives to ticketing\n"
        ),
    ))

    # ── Resources — PRIME OS ──────────────────────────────────────────

    prime_r1 = await store.create_resource(ResourceCreate(
        type=ResourceType.article,
        title="Building a Second Brain — Tiago Forte",
        description="Framework for externalising knowledge into a trusted system. Core inspiration for PRIME's knowledge model.",
        source_url="https://www.buildingasecondbrain.com",
        project_ids=[prime.id],
        tags=["knowledge-management", "pkm", "inspiration"],
    ))
    prime_r2 = await store.create_resource(ResourceCreate(
        type=ResourceType.article,
        title="Local-first Software — Kleppmann et al.",
        description="Academic case for keeping data on user devices. Underpins PRIME's original file-first architecture.",
        source_url="https://www.inkandswitch.com/local-first/",
        project_ids=[prime.id],
        tags=["local-first", "architecture", "data"],
    ))
    prime_n1 = await store.create_resource(ResourceCreate(
        type=ResourceType.note,
        title="PRIME OS Roadmap",
        description="Prioritised development sequence.",
        project_ids=[prime.id],
        tags=["roadmap", "planning"],
        content=(
            "# PRIME OS Roadmap\n\n"
            "## Phase 1 — Done\nFrontend wired to live API. Docker Compose. PostgreSQL.\n\n"
            "## Phase 2 — LiteLLM + real agents\nReplace hardcoded Anthropic SDK. AgentRunner Protocol.\n\n"
            "## Phase 3 — News view\nRSS aggregation, curated AI/tech sources.\n\n"
            "## Phase 4 — IBM pre-sales RAG\nDocument ingestion (URL + PDF), pgvector.\n\n"
            "## Phase 5 — Advanced\nLangfuse, voice interface, multi-agent orchestration.\n"
        ),
    ))

    # ── Edges ─────────────────────────────────────────────────────────

    await store.create_edge(EdgeCreate(
        from_id=soc_n1.id, to_id=soc_r2.id,
        relation=RelationType.references,
        note="Demo architecture depends on WatsonX Orchestrate capabilities",
    ))
    await store.create_edge(EdgeCreate(
        from_id=prime_n1.id, to_id=prime_r2.id,
        relation=RelationType.references,
        note="Roadmap grounded in local-first software principles",
    ))

    print("  Seed complete.")


async def _main():
    """CLI entry point — creates tables then seeds."""
    await create_tables()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            store = DBStore(session)
            # Wipe existing data
            from sqlalchemy import text
            for table in ["edges", "resource_projects", "concepts", "todos", "decisions", "resources", "projects"]:
                await session.execute(text(f"TRUNCATE {table} CASCADE"))
            await seed_db(store)
    print("\nDone. Start the server:")
    print("  docker-compose up")
    print("  # or: uvicorn backend.main:app --port 7474 --reload")


if __name__ == "__main__":
    asyncio.run(_main())
