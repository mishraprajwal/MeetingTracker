"""LangGraph orchestration.

ingest -> coordinator -> [round 1: all role agents in parallel] -> sync
       -> [round 2: role agents read their inbox and revise, in parallel] -> publish
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .agents import ROLES, coordinator_node, make_role_node
from .ingest import load_transcript
from .publishers import publish_node
from .state import MeetingState


def ingest_node(state: MeetingState) -> dict:
    transcript = state.get("transcript") or load_transcript(state["source"])
    return {"transcript": transcript}


def sync_node(state: MeetingState) -> dict:
    """Barrier between rounds; round-1 messages are now in state for round 2 to read."""
    return {}


def build_graph(roles: list[str] | None = None):
    keys = roles or list(ROLES)
    g = StateGraph(MeetingState)
    g.add_node("ingest", ingest_node)
    g.add_node("coordinator", coordinator_node)
    g.add_node("sync", sync_node)
    g.add_node("publish", publish_node)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "coordinator")
    for k in keys:
        g.add_node(f"r1_{k}", make_role_node(k, 1))
        g.add_node(f"r2_{k}", make_role_node(k, 2))
        g.add_edge("coordinator", f"r1_{k}")
        g.add_edge(f"r2_{k}", "publish")
        g.add_edge("sync", f"r2_{k}")
    g.add_edge([f"r1_{k}" for k in keys], "sync")
    g.add_edge("publish", END)
    return g.compile()
