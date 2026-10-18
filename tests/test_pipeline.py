import os

import pytest

from meeting_tracker.agents import ROLES, parse_lines
from meeting_tracker.graph import build_graph
from meeting_tracker.ingest import clean_caption_text

SAMPLE = "samples/onboarding_kickoff.txt"


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("MT_OFFLINE", "1")
    monkeypatch.setenv("MT_OUTPUT_DIR", str(tmp_path))
    for k in list(os.environ):
        if "WEBHOOK" in k:
            monkeypatch.delenv(k)


def test_pipeline_all_agents_report_and_communicate(tmp_path):
    out = build_graph().invoke({"source": SAMPLE, "title": "T"})
    assert set(out["reports"]) == set(ROLES)
    rounds = {m["round"] for m in out["messages"]}
    assert 1 in rounds  # agents handed work to each other
    # a handoff recipient surfaced it as a to-do in round 2
    assert any(t.startswith("Respond to") for r in out["reports"].values() for t in r["todos"])
    assert len(list(tmp_path.glob("t_*.md"))) == len(ROLES) + 1


def test_role_subset():
    out = build_graph(["swe", "qa"]).invoke({"source": SAMPLE, "title": "T"})
    assert set(out["reports"]) == {"swe", "qa"}


def test_due_dates_and_owners():
    out = build_graph(["swe"]).invoke({"source": SAMPLE, "title": "T"})
    items = {(a["owner"], a["due"]) for a in out["context"]["action_items"]}
    assert ("Marcus", "next Friday") in items


def test_vtt_cleaning():
    vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\n<v Ann>Ann: hello there</v>\n"
    assert parse_lines(clean_caption_text(vtt))[0][0] == "Ann"
