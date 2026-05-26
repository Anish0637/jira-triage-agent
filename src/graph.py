"""
LangGraph workflow definition.

Graph shape:
  fetch_tickets
      ↓ (conditional)
  group_by_priority → find_similar → generate_report → END
      ↓ (no tickets / error)
  END
"""

from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes import (
    fetch_tickets_node,
    group_by_priority_node,
    find_similar_node,
    generate_report_node,
)


def _route_after_fetch(state: AgentState) -> str:
    if state.get("error"):
        return "error"
    if not state.get("todays_tickets"):
        return "empty"
    return "continue"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("fetch_tickets", fetch_tickets_node)
    graph.add_node("group_by_priority", group_by_priority_node)
    graph.add_node("find_similar", find_similar_node)
    graph.add_node("generate_report", generate_report_node)

    graph.set_entry_point("fetch_tickets")

    graph.add_conditional_edges(
        "fetch_tickets",
        _route_after_fetch,
        {
            "continue": "group_by_priority",
            "empty": END,
            "error": END,
        },
    )

    graph.add_edge("group_by_priority", "find_similar")
    graph.add_edge("find_similar", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()
