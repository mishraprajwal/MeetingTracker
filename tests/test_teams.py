import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from meeting_tracker.teams import service
from meeting_tracker.teams.graph_client import parse_join_url

CTX = quote(json.dumps({"Tid": "tenant-1", "Oid": "org-1"}))
URL = f"https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc%40thread.v2/1700000000000?context={CTX}"


def test_parse_join_url():
    m = parse_join_url(URL)
    assert m["thread_id"] == "19:meeting_abc@thread.v2"
    assert m["organizer_id"] == "org-1" and m["tenant_id"] == "tenant-1"


def test_bad_url():
    with pytest.raises(ValueError):
        parse_join_url("https://example.com/foo")


def test_process_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("MT_OFFLINE", "1")
    monkeypatch.setenv("MT_OUTPUT_DIR", str(tmp_path))
    for k in ("SLACK_WEBHOOK_URL", "TEAMS_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)

    class FakeGraph:
        def fetch_transcript(self, url):
            return "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nMarcus: I'll deploy the API endpoint by Friday.\n"

    monkeypatch.setattr(service, "_client", FakeGraph())
    c = TestClient(service.app)
    assert c.post("/meetings/process", json={"join_url": "https://x.com/y"}).status_code == 422
    r = c.post("/meetings/process", json={"join_url": URL, "title": "Sync"})
    assert r.status_code == 202
    assert (tmp_path / "sync_swe.md").exists()
