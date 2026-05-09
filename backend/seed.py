"""
Seed script — populates ~/PRIME with example data so you can start
the server and immediately see a live knowledge graph.

Run once:
    python -m backend.seed
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make sure package root is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import settings
from backend.services.file_store import FileStore
from backend.models.project import ProjectCreate, ProjectStatus, DecisionCreate, DecisionType, Alternative, TodoCreate, Priority
from backend.models.resource import ResourceCreate, ResourceType, EdgeCreate, RelationType
from backend.models.agent import AgentCreate, AgentRole, AgentTool


def seed():
    store = FileStore(settings.workspace_path)
    print(f"Seeding workspace at: {settings.workspace_path}")

    # ── Projects ──────────────────────────────────────────────────────

    p1 = store.create_project(ProjectCreate(
        name="Personal AI OS",
        emoji="🤖",
        description="PRIME — Jarvis-style personal assistant with knowledge graph, voice interface, and agent management.",
        color="#00d4ff",
        status=ProjectStatus.active,
        tags=["software", "ai", "personal"],
    ))
    print(f"  Created project: {p1.id}")

    p2 = store.create_project(ProjectCreate(
        name="Home Renovation 2026",
        emoji="🏠",
        description="Bathroom & kitchen renovation — contractor selection, permits, Q3 start.",
        color="#f59e0b",
        status=ProjectStatus.active,
        tags=["home", "renovation"],
    ))
    print(f"  Created project: {p2.id}")

    p3 = store.create_project(ProjectCreate(
        name="Investment Portfolio Q2",
        emoji="📊",
        description="Q2 2026 rebalancing — international ETF shift and auto-rebalance setup.",
        color="#10b981",
        status=ProjectStatus.planning,
        tags=["finance", "investing"],
    ))
    print(f"  Created project: {p3.id}")

    # ── Decisions ─────────────────────────────────────────────────────

    store.create_decision(DecisionCreate(
        project_id=p1.id,
        title="Local-first data storage",
        type=DecisionType.adr,
        context="Need a storage layer for PRIME that is fast, private, and doesn't require external services.",
        body="All data stored as Markdown + JSON files in ~/PRIME. No external database for MVP.",
        consequences="Human-readable, git-trackable. Queries are filesystem scans — acceptable at personal scale.",
        alternatives=[
            Alternative(title="PostgreSQL", reason="Overkill for personal scale; adds infrastructure dependency."),
            Alternative(title="Notion sync", reason="Creates external dependency and data lock-in."),
        ],
        tags=["storage", "architecture"],
    ))

    store.create_decision(DecisionCreate(
        project_id=p1.id,
        title="HTML-first interactive prototype",
        type=DecisionType.adr,
        context="Need to validate the UX and interaction model before committing to a full tech stack.",
        body="Build a rich single-file HTML prototype. Validates all four views quickly without infrastructure.",
        consequences="Fast iteration. Tech stack decision deferred until UX is validated.",
        alternatives=[
            Alternative(title="React SPA", reason="Adds build tooling before UX is validated."),
            Alternative(title="Figma mockup", reason="Not interactive enough to evaluate real feel."),
        ],
        tags=["frontend", "prototype"],
    ))

    store.create_decision(DecisionCreate(
        project_id=p2.id,
        title="Bathroom first, kitchen Q4",
        type=DecisionType.decision,
        context="Renovating both rooms simultaneously would make the home unlivable.",
        body="Start with bathroom Q3 2026. Defer kitchen to Q4 budget permitting.",
        consequences="Kitchen remains functional throughout. Extends overall project timeline.",
        alternatives=[
            Alternative(title="Both simultaneously", reason="Too disruptive to daily life."),
            Alternative(title="Kitchen first", reason="Bathroom is more urgently needed."),
        ],
        tags=["scope", "timeline"],
    ))

    store.create_decision(DecisionCreate(
        project_id=p3.id,
        title="Increase international ETF allocation to 35%",
        type=DecisionType.decision,
        context="Portfolio is overweight domestic large-cap. USD concentration risk and valuation gap vs international.",
        body="Shift 10% from domestic large-cap to VXUS (international developed markets ETF).",
        consequences="Better geographic diversification. Slightly higher tracking error.",
        alternatives=[
            Alternative(title="Add emerging market exposure", reason="Higher volatility, deferred."),
            Alternative(title="Maintain allocation", reason="Leaves USD concentration risk unaddressed."),
        ],
        tags=["allocation", "etf"],
    ))

    # ── Todos ─────────────────────────────────────────────────────────

    for text, prio, section in [
        ("Design knowledge graph schema (RDF vs property graph)", Priority.high, "In Progress"),
        ("Choose voice API — Whisper vs Web Speech", Priority.medium, "Up Next"),
        ("Wire frontend to backend API", Priority.high, "Up Next"),
        ("Set up file-watching for live graph updates", Priority.medium, "Backlog"),
        ("Build interactive prototype", Priority.high, "Done"),
    ]:
        t = store.create_todo(p1.id, TodoCreate(text=text, priority=prio, section=section))
        if section == "Done":
            from backend.models.project import TodoUpdate, TodoStatus
            store.update_todo(p1.id, t.id, TodoUpdate(status=TodoStatus.done))

    for text, prio, section in [
        ("Review BuildRight final quote", Priority.high, "Immediate"),
        ("Get permit status from city office", Priority.high, "Immediate"),
        ("Finalise tile and fixture selection", Priority.medium, "In Progress"),
    ]:
        store.create_todo(p2.id, TodoCreate(text=text, priority=prio, section=section))

    for text, prio, section in [
        ("Execute VXUS purchase order", Priority.high, "This Week"),
        ("Configure auto-rebalance rules", Priority.medium, "This Month"),
    ]:
        store.create_todo(p3.id, TodoCreate(text=text, priority=prio, section=section))

    # ── Concepts ──────────────────────────────────────────────────────

    store.create_concept(p1.id, "Decision archaeology", "Every choice recorded with alternatives, fully queryable later.")
    store.create_concept(p1.id, "Local-first", "Data lives in files. No cloud lock-in.")
    store.create_concept(p1.id, "Knowledge graph", "Entities linked by semantic edges, visualised and navigable.")
    store.create_concept(p2.id, "Wet room design", "Open shower without enclosure — modern and minimalist.")
    store.create_concept(p3.id, "Factor investing", "Tilt toward value and small-cap for long-term premium.")

    # ── Resources ─────────────────────────────────────────────────────

    a1 = store.create_resource(ResourceCreate(
        type=ResourceType.article, title="Building a Second Brain — Tiago Forte",
        description="Framework for capturing and organising knowledge externally.",
        source_url="https://www.buildingasecondbrain.com",
        project_ids=[p1.id], tags=["knowledge-management", "productivity"],
        content="# Building a Second Brain\n\nCore idea: offload knowledge from your head into a trusted external system...",
    ))
    a2 = store.create_resource(ResourceCreate(
        type=ResourceType.article, title="RDF vs Property Graph for Personal Knowledge",
        description="Trade-off analysis of graph data models at personal scale.",
        project_ids=[p1.id], tags=["knowledge-graph", "database", "architecture"],
        content="# RDF vs Property Graph\n\n## RDF\nStandards-compliant, SPARQL queryable...\n\n## Property Graph\nSimpler, local tooling (NetworkX, Neo4j)...",
    ))
    a3 = store.create_resource(ResourceCreate(
        type=ResourceType.article, title="International ETF Diversification 2026 — Morningstar",
        description="Analysis of geographic diversification benefits for retail investors.",
        source_url="https://morningstar.com",
        project_ids=[p3.id], tags=["investing", "etf", "diversification"],
    ))
    a4 = store.create_resource(ResourceCreate(
        type=ResourceType.article, title="Wet Room Design Guide",
        description="Design principles and waterproofing requirements for wet rooms.",
        project_ids=[p2.id], tags=["renovation", "bathroom", "design"],
    ))

    n1 = store.create_resource(ResourceCreate(
        type=ResourceType.note, title="Voice Interface Brainstorm",
        description="Ideas for wake word, ambient mode, and response personality.",
        project_ids=[p1.id], tags=["voice", "ux"],
        content="# Voice Interface Ideas\n\n- Wake word: 'Hey Prime'\n- Ambient mode: always listening, low power\n- Response style: concise by default, verbose on request\n- Show waveform during speaking\n",
    ))
    n2 = store.create_resource(ResourceCreate(
        type=ResourceType.note, title="Contractor Meeting Notes — BuildRight Co.",
        description="Site visit notes from May 3 2026.",
        project_ids=[p2.id], tags=["contractor", "renovation"],
        content="# BuildRight Site Visit — May 3 2026\n\n- Team of 4, estimated 6-week timeline\n- Quote: €18,400 incl. materials\n- References: 3 provided, all checked out positive\n",
    ))
    n3 = store.create_resource(ResourceCreate(
        type=ResourceType.note, title="Q2 Rebalancing Plan",
        description="Step-by-step execution plan for the Q2 portfolio rebalance.",
        project_ids=[p3.id], tags=["portfolio", "rebalancing"],
        content="# Q2 Rebalancing Steps\n\n1. Sell 10% domestic large-cap (SPY)\n2. Buy VXUS equivalent\n3. Set drift threshold to ±5%\n4. Review bond allocation\n",
    ))

    pdf1 = store.create_resource(ResourceCreate(
        type=ResourceType.pdf, title="BuildRight Co. Final Quote",
        description="€18,400 — 6-week timeline. Received May 7 2026.",
        project_ids=[p2.id], tags=["contractor", "quote", "renovation"],
    ))
    pdf2 = store.create_resource(ResourceCreate(
        type=ResourceType.pdf, title="Q1 2026 Performance Report",
        description="+8.2% vs MSCI World benchmark +6.1%.",
        project_ids=[p3.id], tags=["portfolio", "performance"],
    ))

    v1 = store.create_resource(ResourceCreate(
        type=ResourceType.video, title="WWDC 2025 — Designing for Voice",
        description="SwiftUI speech patterns and voice-first UI design session.",
        source_url="https://developer.apple.com/wwdc25",
        project_ids=[p1.id], tags=["voice", "ux", "apple"],
    ))
    v2 = store.create_resource(ResourceCreate(
        type=ResourceType.video, title="Factor Investing Explained — Ben Felix",
        description="Common Sense Investing: value, profitability, and size premiums.",
        source_url="https://youtube.com",
        project_ids=[p3.id], tags=["investing", "factors"],
    ))

    art1 = store.create_resource(ResourceCreate(
        type=ResourceType.artifact, title="UI Mockup v1",
        description="All four PRIME views sketched as interactive prototype.",
        project_ids=[p1.id], tags=["design", "prototype"],
    ))
    art2 = store.create_resource(ResourceCreate(
        type=ResourceType.artifact, title="ADR Log",
        description="All architectural decisions with alternatives considered.",
        project_ids=[p1.id], tags=["decisions", "architecture"],
    ))
    art3 = store.create_resource(ResourceCreate(
        type=ResourceType.artifact, title="Budget Tracker — Renovation",
        description="Excel tracker for renovation costs vs €45k cap.",
        project_ids=[p2.id], tags=["budget", "renovation"],
    ))

    # ── Extra edges (cross-project, resource→resource) ────────────────

    # Note cites the article it references
    store.create_edge(EdgeCreate(from_id=n1.id, to_id=a1.id, relation=RelationType.references,  note="Voice brainstorm references BASB"))
    store.create_edge(EdgeCreate(from_id=n1.id, to_id=v1.id, relation=RelationType.references,  note="WWDC session informed voice design"))
    store.create_edge(EdgeCreate(from_id=art2.id, to_id=a2.id, relation=RelationType.cites,     note="ADR Log cites RDF research"))
    store.create_edge(EdgeCreate(from_id=n3.id, to_id=a3.id, relation=RelationType.references,  note="Rebalancing plan references Morningstar analysis"))
    store.create_edge(EdgeCreate(from_id=a2.id, to_id=n1.id, relation=RelationType.related_to,  note="Graph schema decision affects voice data model"))

    # ── Agents ────────────────────────────────────────────────────────

    store.create_agent(AgentCreate(
        name="Research", role=AgentRole.research, emoji="🔍",
        description="Gathers information, synthesises sources, saves findings.",
        tools=[AgentTool.web_search, AgentTool.write_resource, AgentTool.read_resource,
               AgentTool.create_note, AgentTool.link_resources, AgentTool.list_projects],
    ))
    store.create_agent(AgentCreate(
        name="Writer", role=AgentRole.writer, emoji="✍️",
        description="Writes documents, ADRs, summaries, and briefs.",
        tools=[AgentTool.read_resource, AgentTool.write_resource, AgentTool.create_decision,
               AgentTool.read_project, AgentTool.list_projects],
    ))
    store.create_agent(AgentCreate(
        name="Analyst", role=AgentRole.analyst, emoji="📊",
        description="Analyses data and produces structured reports.",
        tools=[AgentTool.read_resource, AgentTool.write_resource, AgentTool.read_project,
               AgentTool.create_note],
    ))
    store.create_agent(AgentCreate(
        name="Monitor", role=AgentRole.monitor, emoji="👁️",
        description="Watches sources and surfaces important changes.",
        tools=[AgentTool.web_search, AgentTool.create_note, AgentTool.read_project],
    ))

    print("\n✅ Seed complete.")
    print(f"   Projects: 3")
    print(f"   Resources: articles×4, notes×3, pdfs×2, videos×2, artifacts×3")
    print(f"   Agents: Research, Writer, Analyst, Monitor")
    print(f"\nStart the server with:")
    print(f"   cd {Path(__file__).parent.parent}")
    print(f"   uvicorn backend.main:app --host 127.0.0.1 --port 7474 --reload")


if __name__ == "__main__":
    seed()
