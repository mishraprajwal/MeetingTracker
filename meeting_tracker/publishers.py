"""Render role-specific reports and post them to Slack / Microsoft Teams (or a local folder)."""
from __future__ import annotations

import os
import re
from pathlib import Path

import httpx

from .agents import ROLES
from .state import MeetingState


def _bullets(items: list[str]) -> str:
    return "\n".join(f"• {i}" for i in items) if items else "_None_"


def _fmt_action(a: dict) -> str:
    due = f" — due *{a['due']}*" if a.get("due") else ""
    return f"*{a.get('owner', 'Unassigned')}*: {a.get('task', '')}{due}"


def render_role_report(state: MeetingState, role_key: str) -> str:
    role, rep = ROLES[role_key], state["reports"].get(role_key, {})
    inbox = [m for m in state.get("messages", []) if m["to"] in (role_key, "all") and m["sender"] != role_key]
    parts = [
        f"{role.emoji} *{role.name} report — {state.get('title', 'Meeting')}*",
        f"*Summary*\n{rep.get('summary', '')}",
        "*Action items*\n" + _bullets([_fmt_action(a) for a in rep.get("action_items", [])]),
        "*To-dos*\n" + _bullets(rep.get("todos", [])),
        "*Risks / blockers*\n" + _bullets(rep.get("risks", [])),
        "*Open questions*\n" + _bullets(rep.get("questions", [])),
        "*Handoffs from other teams*\n" + _bullets([f"{ROLES[m['sender']].name}: {m['content']}" for m in inbox]),
    ]
    return "\n\n".join(parts)


def render_overview(state: MeetingState) -> str:
    c = state["context"]
    return "\n\n".join([
        f"🗒️ *Meeting overview — {state.get('title', 'Meeting')}*",
        f"*Summary*\n{c.get('summary', '')}",
        f"*Attendees*: {', '.join(c.get('attendees', [])) or 'n/a'}",
        "*Decisions*\n" + _bullets(c.get("decisions", [])),
        "*Action items*\n" + _bullets([_fmt_action(a) for a in c.get("action_items", [])]),
    ])


def _to_markdown(text: str) -> str:
    return re.sub(r"\*(.+?)\*", r"**\1**", text)


def post_slack(url: str, text: str) -> None:
    httpx.post(url, json={"text": text}, timeout=15).raise_for_status()


def post_teams(url: str, text: str) -> None:
    """Adaptive Card payload, accepted by Teams Workflows ('Post to a channel when a webhook request is received')."""
    card = {"type": "message", "attachments": [{
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard",
                    "version": "1.4", "body": [{"type": "TextBlock", "wrap": True, "text": _to_markdown(text)}]},
    }]}
    httpx.post(url, json=card, timeout=15).raise_for_status()


def _webhook(prefix: str, key: str) -> str | None:
    return os.getenv(f"{prefix}_WEBHOOK_{key.upper()}") or os.getenv(f"{prefix}_WEBHOOK_URL")


def publish_node(state: MeetingState) -> dict:
    """Per-role channel webhook (SLACK_WEBHOOK_SWE) falls back to the shared SLACK_WEBHOOK_URL; same for TEAMS."""
    out_dir = Path(os.getenv("MT_OUTPUT_DIR", "output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"\W+", "_", state.get("title", "meeting")).strip("_").lower() or "meeting"

    posts = [("overview", render_overview(state))] + [(k, render_role_report(state, k)) for k in state["reports"]]
    log: list[str] = []
    for key, text in posts:
        (out_dir / f"{stem}_{key}.md").write_text(_to_markdown(text), encoding="utf-8")
        log.append(f"saved {out_dir}/{stem}_{key}.md")
        for name, prefix, sender in (("slack", "SLACK", post_slack), ("teams", "TEAMS", post_teams)):
            url = _webhook(prefix, key)
            if not url or os.getenv("MT_DRY_RUN") == "1":
                continue
            try:
                sender(url, text)
                log.append(f"posted {key} -> {name}")
            except httpx.HTTPError as e:
                log.append(f"FAILED {key} -> {name}: {e}")
    return {"published": log}
