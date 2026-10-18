"""Agent definitions: a Coordinator plus role-specific agents that talk to each other.

Every agent has an LLM path (any OpenAI-compatible model) and a deterministic
heuristic path so the pipeline runs offline for demos/tests.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .llm import complete_json, llm_available
from .state import MeetingState, Message


@dataclass(frozen=True)
class Role:
    key: str
    name: str
    focus: str
    keywords: tuple[str, ...]
    emoji: str = ""


ROLES: dict[str, Role] = {r.key: r for r in [
    Role("pm", "Product Manager", "scope, priorities, roadmap, deadlines, stakeholder commitments, customer impact",
         ("roadmap", "priority", "deadline", "launch", "release", "customer", "scope", "milestone", "stakeholder", "timeline"), "🧭"),
    Role("swe", "Software Engineer", "implementation tasks, architecture, APIs, bugs, tech debt, dependencies, estimates",
         ("api", "backend", "frontend", "code", "bug", "deploy", "database", "migration", "refactor", "endpoint", "service", "infrastructure"), "💻"),
    Role("ds", "Data Scientist", "metrics, experiments, models, datasets, analytics, data quality",
         ("model", "metric", "data", "experiment", "a/b", "dashboard", "analytics", "accuracy", "dataset", "forecast", "churn", "pipeline"), "📊"),
    Role("ba", "Business Analyst", "requirements, user stories, acceptance criteria, process, business rules, ROI",
         ("requirement", "user story", "acceptance", "process", "compliance", "business", "stakeholder", "budget", "cost", "revenue", "policy"), "📋"),
    Role("qa", "QA Engineer", "test plans, regressions, edge cases, release readiness, defects, automation",
         ("test", "qa", "regression", "bug", "defect", "edge case", "coverage", "automation", "quality", "release", "flaky"), "🧪"),
    Role("design", "Product Designer", "UX flows, UI changes, research, accessibility, design system, usability",
         ("design", "ux", "ui", "mockup", "wireframe", "figma", "prototype", "accessibility", "usability", "flow", "layout", "onboarding"), "🎨"),
]}

DUE_RE = re.compile(r"\b(?:by|before|until|due)\s+((?:next\s+|this\s+)?(?:mon|tues|wednes|thurs|fri|satur|sun)day|tomorrow|eod|end of (?:day|week|month|sprint)|\d{1,2}/\d{1,2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2})", re.I)
ACTION_RE = re.compile(r"\b(i'll|i will|we'll|we will|will|going to|need to|needs to|must|should|todo|action item|let me|can you|please)\b", re.I)
DECISION_RE = re.compile(r"\b(decided|agreed|decision|let's go with|we're going with|approved|signed off|settled on)\b", re.I)
RISK_RE = re.compile(r"\b(risk|blocker|blocked|concern|worried|delay|slip|dependency|unclear|problem)\b", re.I)


def parse_lines(transcript: str) -> list[tuple[str, str]]:
    """Split a transcript into (speaker, sentence) pairs; speaker is '' if unlabeled."""
    out = []
    for line in transcript.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(?:\[[^\]]*\]\s*)?([A-Za-z][\w .'-]{0,40}):\s+(.*)$", line)
        speaker, text = (m.group(1).strip(), m.group(2)) if m else ("", line)
        for s in re.split(r"(?<=[.!?])\s+", text):
            if s.strip():
                out.append((speaker, s.strip()))
    return out


def _hits(text: str, role: Role) -> bool:
    return any(re.search(rf"\b{re.escape(k)}\w*", text, re.I) for k in role.keywords)


def _action(speaker: str, sentence: str) -> dict:
    due = DUE_RE.search(sentence)
    return {"owner": speaker or "Unassigned", "task": sentence, "due": due.group(1) if due else None}


# ---------------------------------------------------------------- Coordinator
def coordinator_node(state: MeetingState) -> dict:
    """Reads the raw transcript once and produces the shared context every role agent builds on."""
    transcript = state["transcript"]
    if llm_available():
        ctx = complete_json(
            "You are the meeting Coordinator agent. Extract shared facts from the transcript.\n"
            'Return JSON: {"summary": str (3-5 sentences), "attendees": [str], "decisions": [str], '
            '"action_items": [{"owner": str, "task": str, "due": str|null}], "open_questions": [str], "risks": [str]}',
            transcript[:60000],
        )
    else:
        pairs = parse_lines(transcript)
        speakers = list(dict.fromkeys(s for s, _ in pairs if s))
        ctx = {
            "summary": " ".join(t for _, t in pairs[:4]),
            "attendees": speakers,
            "decisions": [t for _, t in pairs if DECISION_RE.search(t)],
            "action_items": [_action(s, t) for s, t in pairs if ACTION_RE.search(t) and not t.endswith("?")],
            "open_questions": [t for _, t in pairs if t.endswith("?")],
            "risks": [t for _, t in pairs if RISK_RE.search(t)],
        }
    return {"context": ctx}


# ---------------------------------------------------------------- Role agents
REPORT_SCHEMA = (
    '{"summary": str, "action_items": [{"owner": str, "task": str, "due": str|null}], '
    '"todos": [str], "risks": [str], "questions": [str], '
    '"messages": [{"to": "<role key or all>", "content": str}]}'
)


def _inbox(state: MeetingState, role: Role, rnd: int) -> list[Message]:
    return [m for m in state.get("messages", [])
            if m["round"] < rnd and m["sender"] != role.key and m["to"] in (role.key, "all")]


def _heuristic_report(state: MeetingState, role: Role, rnd: int) -> dict:
    ctx = state["context"]
    pairs = parse_lines(state["transcript"])
    mine = [(s, t) for s, t in pairs if _hits(t, role)]
    actions = [a for a in ctx.get("action_items", []) if _hits(a["task"], role)]
    risks = [r for r in ctx.get("risks", []) if _hits(r, role)]
    questions = [q for q in ctx.get("open_questions", []) if _hits(q, role)]

    messages = []
    if rnd == 1:  # hand off anything touching another discipline
        for _, text in mine:
            for other in ROLES.values():
                if other.key != role.key and _hits(text, other):
                    # Only hand off sentences that are actionable or risky
                    if ACTION_RE.search(text) or RISK_RE.search(text) or text.endswith("?"):
                        messages.append({"to": other.key, "content": text})
        seen, dedup = set(), []
        for m in messages:
            k = (m["to"], m["content"])
            if k not in seen:
                seen.add(k)
                dedup.append(m)
        messages = dedup[:6]

    todos = [f"{a['task']}" + (f" (due {a['due']})" if a.get("due") else "") for a in actions]
    for m in _inbox(state, role, rnd):
        todos.append(f"Respond to {ROLES[m['sender']].name}: {m['content']}")
    summary = " ".join(t for _, t in mine[:3]) or "No discussion directly relevant to this role."
    return {"summary": summary, "action_items": actions, "todos": todos,
            "risks": risks, "questions": questions, "messages": messages}


def _llm_report(state: MeetingState, role: Role, rnd: int) -> dict:
    ctx = state["context"]
    inbox = _inbox(state, role, rnd)
    system = (
        f"You are the {role.name} agent on a multi-agent meeting-tracking team. "
        f"Your focus: {role.focus}. Produce a report only for what matters to your role; "
        "never invent facts not in the transcript. Use the `messages` field to hand off questions, "
        "dependencies or risks to OTHER roles (keys: " + ", ".join(ROLES) + ") — only when truly needed.\n"
        f"Return JSON: {REPORT_SCHEMA}"
    )
    user = f"Shared context from Coordinator:\n{json.dumps(ctx)}\n\nTranscript:\n{state['transcript'][:50000]}\n"
    if rnd == 2:
        user += (f"\nThis is round 2. Your previous report:\n{json.dumps(state['reports'].get(role.key, {}))}\n"
                 f"Messages other agents sent you:\n{json.dumps(inbox)}\n"
                 "Revise your report: add todos/risks resulting from these messages. "
                 "Use `messages` only for replies to the senders.")
    return complete_json(system, user)


def make_role_node(role_key: str, rnd: int):
    role = ROLES[role_key]

    def node(state: MeetingState) -> dict:
        data = _llm_report(state, role, rnd) if llm_available() else _heuristic_report(state, role, rnd)
        out_msgs: list[Message] = []
        for m in data.pop("messages", []) or []:
            to = m.get("to")
            if (to in ROLES and to != role_key) or to == "all":
                out_msgs.append({"sender": role_key, "to": to, "content": str(m.get("content", "")), "round": rnd})
        return {"reports": {role_key: data}, "messages": out_msgs}

    node.__name__ = f"r{rnd}_{role_key}"
    return node
