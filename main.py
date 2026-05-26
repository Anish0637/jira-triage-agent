#!/usr/bin/env python3
"""
Entry point for the Jira LangGraph Triage Agent.

Usage
-----
# First time: index resolved tickets from the dashboard into Pinecone
python main.py --index-resolved

# Daily triage run scoped to dashboard 12042 (default)
python main.py

# Override dashboard or add a project key scope
python main.py --dashboard 12042 --project NET
"""

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()  # load .env before any src imports touch os.environ

DEFAULT_DASHBOARD_ID = os.getenv("JIRA_DASHBOARD_ID", "12042")


def run_agent(dashboard_id: str | None, project_key: str | None) -> None:
    from src.graph import build_graph

    graph = build_graph()
    initial_state = {
        "dashboard_id": dashboard_id,
        "dashboard_context": None,
        "project_key": project_key,
        "todays_tickets": [],
        "grouped_tickets": {},
        "tickets_with_similar": [],
        "report": "",
        "error": None,
    }

    label = f"dashboard {dashboard_id}" if dashboard_id else (f"project {project_key}" if project_key else "all projects")
    print(f"Running triage agent for {label}…\n")
    final_state = graph.invoke(initial_state)

    if final_state.get("error"):
        print(f"[ERROR] {final_state['error']}", file=sys.stderr)
        sys.exit(1)

    tickets = final_state.get("todays_tickets", [])
    if not tickets:
        print("No tickets created in the last 7 days. Nothing to triage.")
        return

    ctx = final_state.get("dashboard_context") or {}
    if ctx.get("name"):
        print(f"Dashboard : {ctx['name']}")
        if ctx.get("filter_ids"):
            print(f"Filters   : {', '.join(ctx['filter_ids'])}")
        else:
            print("Filters   : none resolved — used fallback JQL")
    print(f"Tickets   : {len(tickets)} created in the last 7 days\n")

    # --- Priority summary table ---
    print("Priority breakdown:")
    for priority, group in final_state["grouped_tickets"].items():
        print(f"  {priority:12s}  {len(group)}")

    # --- Semantic matches (raw) ---
    print("\nSemantic matches:")
    for item in final_state["tickets_with_similar"]:
        t = item["ticket"]
        print(f"\n  [{t['key']}] {t['summary']}")
        for s in item["similar_resolved"]:
            print(f"    score={s['score']:.2f}  [{s['key']}] {s['summary']}  ({s['resolution']})")

    # --- LLM triage report ---
    print("\n" + "=" * 70)
    print("TRIAGE REPORT")
    print("=" * 70)
    print(final_state["report"])
    print("=" * 70)


def run_index(dashboard_id: str | None, project_key: str | None) -> None:
    from src.jira_client import fetch_dashboard_context, fetch_resolved_tickets
    from src.pinecone_store import index_resolved_tickets

    ctx = None
    if dashboard_id:
        print(f"Resolving dashboard {dashboard_id}…")
        ctx = fetch_dashboard_context(dashboard_id)
        print(f"Dashboard: '{ctx['name']}' | filters: {ctx['filter_ids'] or 'none'}")

    print("Fetching resolved tickets…")
    tickets = fetch_resolved_tickets(
        project_key=project_key, dashboard_context=ctx, max_results=1000
    )
    print(f"Fetched {len(tickets)} resolved tickets. Indexing into Pinecone…")
    index_resolved_tickets(tickets)
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jira LangGraph Triage Agent")
    parser.add_argument(
        "--dashboard", "-d", metavar="ID",
        default=DEFAULT_DASHBOARD_ID,
        help=f"Jira dashboard ID (default: {DEFAULT_DASHBOARD_ID})",
    )
    parser.add_argument("--project", "-p", metavar="KEY", help="Jira project key (e.g. NET)")
    parser.add_argument(
        "--index-resolved",
        action="store_true",
        help="Embed & upsert resolved tickets into Pinecone (run once before triage)",
    )
    args = parser.parse_args()

    if args.index_resolved:
        run_index(dashboard_id=args.dashboard, project_key=args.project)
    else:
        run_agent(dashboard_id=args.dashboard, project_key=args.project)
