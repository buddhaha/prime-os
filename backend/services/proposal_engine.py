"""
PRIME OS — ProposalEngine

Detects knowledge gaps in a project and generates document proposals using
web search + Claude to fill them.

Gap detection (structural — no external calls):
  - Concepts with no linked resources
  - High-priority open todos with no linked resources
  - Decisions with alternatives that have no source material

Proposal generation (Claude + web search):
  - Given a gap, search for the best resource
  - Generate why_relevant (project-specific, 2-3 sentences)
  - Generate 3 concrete takeaways
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import anthropic

from .db_store import DBStore
from ..models.resource import ProposalCreate, ResourceType

log = logging.getLogger("prime.proposals")

# How many proposals to generate per analysis run (cap to avoid spamming)
MAX_PROPOSALS_PER_RUN = 5


# ─────────────────────────────────────────────
# Gap dataclass
# ─────────────────────────────────────────────

@dataclass
class Gap:
    gap_type:  str   # "concept" | "todo" | "decision"
    gap_label: str   # name/title of the gap source
    context:   str   # extra context for the generator (project description + surrounding data)


# ─────────────────────────────────────────────
# Gap detection
# ─────────────────────────────────────────────

async def detect_gaps(store: DBStore, project_id: str) -> list[Gap]:
    """
    Scan the project for knowledge gaps — things referenced but unsourced.
    Returns a ranked list of gaps (most important first).
    """
    gaps: list[Gap] = []

    detail = await store.get_project_detail(project_id)
    if not detail:
        return gaps

    project     = detail.project
    concepts    = detail.concepts
    todos       = detail.todos
    decisions   = detail.decisions
    resources   = await store.list_resources(project_id=project_id)

    project_ctx = (
        f"Project: {project.name}\n"
        f"Description: {project.description}\n"
        f"Tags: {', '.join(project.tags)}"
    )

    # 1. Concepts with no linked resource (match by name substring in resource title/tags)
    resource_titles_lower = [r.title.lower() for r in resources]
    resource_tags_flat    = [t.lower() for r in resources for t in r.tags]

    for concept in concepts:
        name_lower = concept.name.lower()
        covered = any(name_lower in t for t in resource_titles_lower) or \
                  any(name_lower in t for t in resource_tags_flat)
        if not covered:
            gaps.append(Gap(
                gap_type="concept",
                gap_label=concept.name,
                context=(
                    f"{project_ctx}\n"
                    f"Concept: {concept.name}\n"
                    f"Definition: {concept.desc}\n"
                    f"This concept is referenced in the project but has no linked source material."
                ),
            ))

    # 2. High-priority open todos with no matched resource
    for todo in todos:
        if todo.status != "open" or todo.priority not in ("high",):
            continue
        text_lower = todo.text.lower()
        covered = any(
            word in " ".join(resource_titles_lower + resource_tags_flat)
            for word in text_lower.split()
            if len(word) > 4
        )
        if not covered:
            gaps.append(Gap(
                gap_type="todo",
                gap_label=todo.text[:80],
                context=(
                    f"{project_ctx}\n"
                    f"High-priority todo: {todo.text}\n"
                    f"No resource currently covers this task."
                ),
            ))

    # 3. Decisions with unresourced alternatives
    for decision in decisions:
        for alt in (decision.alternatives or []):
            alt_name = alt.get("title", "") if isinstance(alt, dict) else getattr(alt, "title", "")
            if not alt_name:
                continue
            covered = any(alt_name.lower() in t for t in resource_titles_lower)
            if not covered:
                gaps.append(Gap(
                    gap_type="decision",
                    gap_label=alt_name,
                    context=(
                        f"{project_ctx}\n"
                        f"Decision: {decision.title}\n"
                        f"Alternative considered but not chosen: {alt_name}\n"
                        f"No resource evaluating this alternative exists."
                    ),
                ))

    # Deduplicate and cap
    seen: set[str] = set()
    unique: list[Gap] = []
    for g in gaps:
        key = f"{g.gap_type}:{g.gap_label}"
        if key not in seen:
            seen.add(key)
            unique.append(g)

    return unique[:MAX_PROPOSALS_PER_RUN]


# ─────────────────────────────────────────────
# Proposal generation
# ─────────────────────────────────────────────

_PROPOSAL_SYSTEM = """\
You are PRIME OS, a personal intelligence assistant. Given a knowledge gap in a project, \
you find the most relevant external resource to fill it and write a concise proposal card.

You must respond with valid JSON only — no markdown, no preamble.

JSON schema:
{
  "title": "full title of the recommended resource",
  "resource_type": "article" | "pdf" | "video" | "note" | "link",
  "source_url": "URL or null",
  "read_time": "e.g. '18 min read' or '24 min watch' or null",
  "why_relevant": "2-3 sentences explaining why this fills the gap for THIS project specifically",
  "takeaways": ["sentence 1", "sentence 2", "sentence 3"]
}

Rules:
- why_relevant must reference specific details from the project (names, KPIs, decisions)
- takeaways must be concrete facts, not generic summaries
- prefer real, findable resources (official docs, research papers, reputable articles)
- if a real URL is unknown, set source_url to null rather than fabricating one
"""


async def generate_proposal(gap: Gap, api_key: str) -> dict[str, Any] | None:
    """Call Claude to generate a proposal for a single gap. Returns raw dict or None on failure."""
    client = anthropic.AsyncAnthropic(api_key=api_key)

    prompt = (
        f"Knowledge gap to fill:\n\n{gap.context}\n\n"
        f"Find the best external resource (article, PDF, video, or documentation) "
        f"that would fill this gap. Write the proposal card."
    )

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_PROPOSAL_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        log.warning(f"Proposal generation failed for gap '{gap.gap_label}': {e}")
        return None


# ─────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────

async def run_analysis(store: DBStore, project_id: str, api_key: str) -> list[str]:
    """
    Detect gaps, generate proposals for each, persist to DB.
    Returns list of created proposal IDs.
    """
    log.info(f"Running proposal analysis for project {project_id}")

    gaps = await detect_gaps(store, project_id)
    if not gaps:
        log.info("No gaps found.")
        return []

    # Skip gaps that already have a pending proposal
    existing = await store.list_proposals(project_id=project_id, status="pending")
    existing_labels = {p.gap_label for p in existing}
    gaps = [g for g in gaps if g.gap_label not in existing_labels]

    log.info(f"Found {len(gaps)} new gaps to fill")

    created_ids: list[str] = []
    for gap in gaps:
        raw = await generate_proposal(gap, api_key)
        if not raw:
            continue

        try:
            resource_type = ResourceType(raw.get("resource_type", "article"))
        except ValueError:
            resource_type = ResourceType.article

        proposal = await store.create_proposal(ProposalCreate(
            project_id=project_id,
            title=raw.get("title", "Untitled"),
            resource_type=resource_type,
            source_url=raw.get("source_url"),
            read_time=raw.get("read_time"),
            why_relevant=raw.get("why_relevant", ""),
            takeaways=raw.get("takeaways", []),
            gap_type=gap.gap_type,
            gap_label=gap.gap_label,
        ))
        created_ids.append(proposal.id)
        log.info(f"  Created proposal: {proposal.title}")

    log.info(f"Analysis complete — {len(created_ids)} proposals created")
    return created_ids
