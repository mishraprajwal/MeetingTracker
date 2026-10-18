# MeetingTracker

A multi-agent pipeline, orchestrated with **LangGraph**, that turns a meeting transcript or recording into role-specific reports (summary, action items, to-dos, risks, open questions) and posts them to Slack and/or Microsoft Teams.

## Pipeline

```
ingest ─▶ coordinator ─▶ ┌ r1_pm ┐          ┌ r2_pm ┐
                         │ r1_swe│          │ r2_swe│
                         │ r1_ds │─▶ sync ─▶│ r2_ds │─▶ publish ─▶ Slack / Teams / ./output/*.md
                         │ r1_ba │          │ r2_ba │
                         │ r1_qa │          │ r2_qa │
                         └ r1_design┘       └ r2_design┘
```

- **Coordinator** extracts shared facts once: summary, attendees, decisions, action items, risks, questions.
- **Role agents** (PM, SWE, Data Scientist, BA, QA, Product Designer) run in parallel, each producing a report for their discipline.
- **Agent-to-agent communication:** in round 1 each agent can send messages (handoffs, dependencies, risks) to other roles via shared graph state. After a barrier, round 2 agents read their inbox and revise their reports (e.g. QA gets "migration blocks your tests" from SWE).
- **Publisher** renders one report per role plus an overview; posts each to its own channel webhook.

Add a role by adding a `Role` entry in [agents.py](meeting_tracker/agents.py).

## Getting meeting content

| Source | Support |
|---|---|
| Transcript `.txt` (`Speaker: text` lines), `.vtt`, `.srt` | Direct. Export from Zoom/Teams/Meet/Otter, etc. |
| Audio/video recording (`.mp3 .mp4 .m4a .wav .webm`) | Transcribed with OpenAI Whisper (25 MB API limit). |
| Live recording of calls | Not built in: bots joining meetings need platform-specific APIs (Zoom/Teams/Meet). Use the platform's cloud recording/transcript and feed the file here. |

## Usage

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add keys / webhooks

python -m meeting_tracker samples/onboarding_kickoff.txt --title "Onboarding Kickoff"
python -m meeting_tracker call.mp4 --roles swe,qa
```

- Without `OPENAI_API_KEY` (or with `MT_OFFLINE=1`) agents use keyword heuristics: good for demos and tests, much weaker than the LLM path.
- Reports are always saved to `output/`. They are posted only where a webhook is configured; `MT_DRY_RUN=1` disables posting.
- Slack: create an incoming webhook per channel. Teams: create a Workflows "Post to a channel when a webhook request is received" flow. Per-role variables look like `SLACK_WEBHOOK_SWE`; `*_WEBHOOK_URL` is the fallback.

## Tests

```bash
pytest
```
