"""CLI: python -m meeting_tracker <transcript-or-recording> [--title T] [--roles swe,qa]"""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from .agents import ROLES
from .graph import build_graph


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(prog="meeting_tracker")
    p.add_argument("source", help="Transcript (.txt/.vtt/.srt) or recording (.mp3/.mp4/.wav/...)")
    p.add_argument("--title", help="Meeting title (default: file name)")
    p.add_argument("--roles", help=f"Comma-separated subset of: {','.join(ROLES)}")
    args = p.parse_args(argv)

    roles = [r.strip() for r in args.roles.split(",")] if args.roles else None
    if roles and (bad := [r for r in roles if r not in ROLES]):
        p.error(f"unknown roles: {bad}")

    result = build_graph(roles).invoke({"source": args.source, "title": args.title or Path(args.source).stem})
    from .publishers import render_overview, render_role_report
    print(render_overview(result))
    for k in result["reports"]:
        print("\n" + "=" * 60 + "\n" + render_role_report(result, k))
    print("\n" + "\n".join(result["published"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
