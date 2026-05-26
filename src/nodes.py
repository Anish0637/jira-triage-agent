"""
LangGraph node functions — each takes AgentState and returns a partial update.
"""

import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from .state import AgentState
from .jira_client import fetch_dashboard_context, fetch_todays_tickets
from .pinecone_store import find_similar

# Severity order: highest first
PRIORITY_ORDER = [
    "Blocker", "Critical", "High", "Major",
    "Medium", "Minor", "Low", "Trivial", "Unknown",
]

_llm = ChatOpenAI(model="gpt-4o", temperature=0)


# ---------------------------------------------------------------------------
# Node 1 — Fetch today's Jira tickets
# ---------------------------------------------------------------------------

def fetch_tickets_node(state: AgentState) -> dict:
    try:
        # Resolve dashboard context (filter JQL) on every run
        dashboard_id = state.get("dashboard_id")
        ctx = None
        if dashboard_id:
            ctx = fetch_dashboard_context(dashboard_id)
            print(f"Dashboard: '{ctx['name']}' "
                  f"| filters found: {len(ctx['filter_ids'])} "
                  f"| JQL fragments: {len(ctx['jql_fragments'])}")

        tickets = fetch_todays_tickets(
            project_key=state.get("project_key"),
            dashboard_context=ctx,
        )
        return {"dashboard_context": ctx, "todays_tickets": tickets, "error": None}
    except Exception as exc:
        return {"dashboard_context": None, "todays_tickets": [], "error": str(exc)}


# ---------------------------------------------------------------------------
# Node 2 — Group by priority/severity
# ---------------------------------------------------------------------------

def group_by_priority_node(state: AgentState) -> dict:
    grouped: dict[str, list[dict]] = {}
    for ticket in state["todays_tickets"]:
        priority = ticket.get("priority", "Unknown")
        grouped.setdefault(priority, []).append(ticket)

    # Reorder according to PRIORITY_ORDER; append any unknown labels at the end
    ordered: dict[str, list[dict]] = {k: grouped[k] for k in PRIORITY_ORDER if k in grouped}
    for k, v in grouped.items():
        if k not in ordered:
            ordered[k] = v

    return {"grouped_tickets": ordered}


# ---------------------------------------------------------------------------
# Node 3 — Semantic search for similar resolved tickets
# ---------------------------------------------------------------------------

def find_similar_node(state: AgentState) -> dict:
    results = []
    for ticket in state["todays_tickets"]:
        similar = find_similar(ticket, top_k=3)
        results.append({"ticket": ticket, "similar_resolved": similar})
    return {"tickets_with_similar": results}


# ---------------------------------------------------------------------------
# Node 4 — LLM triage report
# ---------------------------------------------------------------------------

def generate_report_node(state: AgentState) -> dict:
    similar_map = {
        item["ticket"]["key"]: item["similar_resolved"]
        for item in state["tickets_with_similar"]
    }

    lines: list[str] = []
    for priority, tickets in state["grouped_tickets"].items():
        lines.append(f"\n### {priority} ({len(tickets)} ticket(s))")
        for t in tickets:
            lines.append(f"- [{t['key']}] {t['summary']}")
            for s in similar_map.get(t["key"], []):
                flag = " ⚑ STRONG MATCH" if s["score"] >= 0.80 else ""
                lines.append(
                    f"  ↳ Similar resolved: [{s['key']}] {s['summary']} "
                    f"(score {s['score']}, resolution: {s['resolution']}){flag}"
                )

    ctx = state.get("dashboard_context") or {}
    dash_label = f"**{ctx['name']}** (dashboard)" if ctx.get("name") else "Jira"

    prompt = f"""You are a Jira triage assistant for {dash_label}. \
Below are today's newly created tickets grouped by severity, \
with semantically similar resolved tickets shown beneath each one.

{chr(10).join(lines)}

Write a concise, actionable triage report that:
1. States the total ticket count broken down by priority.
2. Calls out every Blocker or Critical ticket by key and summary.
3. For any ticket with a similar resolved match (score ≥ 0.80), recommend reviewing \
   that resolved ticket's resolution before assigning work.
4. Closes with 3–5 prioritised next-action bullet points for the on-call team.

Be brief and direct — this will be pasted into a Slack channel."""

    response = _llm.invoke([HumanMessage(content=prompt)])
    return {"report": response.content}
