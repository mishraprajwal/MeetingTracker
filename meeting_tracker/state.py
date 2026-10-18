"""Shared pipeline state passed between LangGraph nodes."""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class Message(TypedDict):
    """Agent-to-agent message (the inter-agent communication channel)."""
    sender: str
    to: str  # role key or "all"
    content: str
    round: int


def merge_dicts(a: dict, b: dict) -> dict:
    return {**(a or {}), **(b or {})}


class MeetingState(TypedDict, total=False):
    source: str                      # path to transcript / audio file
    title: str
    transcript: str
    context: dict[str, Any]          # coordinator output: summary, decisions, action_items, ...
    # Reducers let parallel agents write concurrently without clobbering each other.
    messages: Annotated[list[Message], operator.add]
    reports: Annotated[dict[str, dict], merge_dicts]
    published: list[str]
