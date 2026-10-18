"""FastAPI service: fetch a Teams meeting transcript via Microsoft Graph and run the agent pipeline.

Run: uvicorn meeting_tracker.teams.service:app --port 8000

POST /meetings/process   {"join_url": "...", "title": "..."}   -> 202; transcript is polled in the
                          background (it appears a few minutes after the meeting ends), then reports are posted.
"""
from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from ..graph import build_graph
from ..ingest import clean_caption_text
from .graph_client import GraphClient, parse_join_url

log = logging.getLogger("meeting_tracker.teams")
app = FastAPI(title="MeetingTracker Teams transcripts")

_client: GraphClient | None = None


def graph_client() -> GraphClient:
    global _client
    _client = _client or GraphClient()
    return _client


class ProcessRequest(BaseModel):
    join_url: str
    title: str = "Teams meeting"


def process_meeting(join_url: str, title: str) -> None:
    vtt = graph_client().fetch_transcript(join_url)
    transcript = clean_caption_text(vtt) if vtt else ""
    if not transcript.strip():
        log.error("No transcript available for %s (is transcription enabled in the meeting?)", title)
        return
    result = build_graph().invoke({"transcript": transcript, "title": title})
    log.info("Published: %s", result.get("published"))


@app.post("/meetings/process", status_code=202)
def process(req: ProcessRequest, background: BackgroundTasks):
    try:
        parse_join_url(req.join_url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    background.add_task(process_meeting, req.join_url, req.title)
    return {"status": "queued"}
