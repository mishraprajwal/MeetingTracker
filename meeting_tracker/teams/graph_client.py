"""Microsoft Graph client: look up a Teams meeting and fetch its transcript."""
from __future__ import annotations

import json
import os
import time
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import msal

GRAPH = "https://graph.microsoft.com/v1.0"


def parse_join_url(join_url: str) -> dict:
    """Extract thread id, message id, tenant and organizer from a Teams join URL."""
    u = urlparse(join_url)
    parts = [p for p in u.path.split("/") if p]
    if "meetup-join" not in parts or len(parts) < parts.index("meetup-join") + 3:
        raise ValueError("Not a Teams meetup-join URL")
    i = parts.index("meetup-join")
    ctx = json.loads(unquote(parse_qs(u.query).get("context", ["{}"])[0]))
    if "Tid" not in ctx or "Oid" not in ctx:
        raise ValueError("Join URL has no context (Tid/Oid)")
    return {"thread_id": unquote(parts[i + 1]), "message_id": parts[i + 2],
            "tenant_id": ctx["Tid"], "organizer_id": ctx["Oid"]}


class GraphClient:
    def __init__(self, tenant_id: str | None = None, client_id: str | None = None, client_secret: str | None = None):
        tenant_id = tenant_id or os.environ["TEAMS_TENANT_ID"]
        self._app = msal.ConfidentialClientApplication(
            client_id or os.environ["TEAMS_CLIENT_ID"],
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret or os.environ["TEAMS_CLIENT_SECRET"],
        )

    def _headers(self) -> dict:
        tok = self._app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in tok:
            raise RuntimeError(f"Graph auth failed: {tok.get('error_description', tok)}")
        return {"Authorization": f"Bearer {tok['access_token']}"}

    def fetch_transcript(self, join_url: str, attempts: int = 12, delay: float = 30.0) -> str | None:
        """Poll for the Teams-generated transcript (it appears some minutes after the meeting ends)."""
        organizer = parse_join_url(join_url)["organizer_id"]
        for n in range(attempts):
            text = self._try_fetch_transcript(organizer, join_url)
            if text:
                return text
            if n < attempts - 1:
                time.sleep(delay)
        return None

    def _try_fetch_transcript(self, organizer: str, join_url: str) -> str | None:
        h = self._headers()
        base = f"{GRAPH}/users/{organizer}/onlineMeetings"
        flt = join_url.replace("'", "''")
        r = httpx.get(base, headers=h, params={"$filter": f"JoinWebUrl eq '{flt}'"}, timeout=30)
        r.raise_for_status()
        meetings = r.json().get("value", [])
        if not meetings:
            return None
        r = httpx.get(f"{base}/{meetings[0]['id']}/transcripts", headers=h, timeout=30)
        r.raise_for_status()
        items = r.json().get("value", [])
        if not items:
            return None
        r = httpx.get(f"{base}/{meetings[0]['id']}/transcripts/{items[-1]['id']}/content",
                      headers=h, params={"$format": "text/vtt"}, timeout=60)
        r.raise_for_status()
        return r.text
