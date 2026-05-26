"""
HITL (Human-in-the-Loop) LangGraph for ticket assignment.

Flow:
  propose → send_email → await_approval [interrupt] → apply / end
"""

import json
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from .dummy_users import DUMMY_USERS
from .email_notifier import send_approval_email


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AssignmentState(TypedDict):
    ticket: dict
    proposed_user: Optional[dict]      # set by propose_node
    approval_status: Optional[str]     # "pending" | "approved" | "rejected"
    rejection_reason: Optional[str]
    email_sent: bool


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

_llm = ChatOpenAI(model="gpt-4o", temperature=0)


def propose_node(state: AssignmentState) -> dict:
    """LLM picks the best dummy user for this ticket."""
    ticket = state["ticket"]
    users_text = "\n".join(
        f'  id="{u["id"]}"  {u["name"]} ({u["role"]}): {", ".join(u["speciality"])}'
        for u in DUMMY_USERS
    )
    prompt = f"""Assign this Jira ticket to the most suitable team member.

Ticket [{ticket['key']}]: {ticket['summary']}
Priority: {ticket['priority']}
Description: {ticket.get('description', '')[:400]}

Available team members:
{users_text}

Reply with ONLY valid JSON (no markdown):
{{"user_id": "<id from above>", "reason": "<one concise sentence>"}}"""

    resp = _llm.invoke([HumanMessage(content=prompt)])
    try:
        raw = resp.content.strip().lstrip("```json").rstrip("```").strip()
        data = json.loads(raw)
        user = next((u for u in DUMMY_USERS if u["id"] == data["user_id"]), DUMMY_USERS[0])
        return {"proposed_user": {**user, "reason": data.get("reason", "")}}
    except Exception:
        return {"proposed_user": {**DUMMY_USERS[0], "reason": "Default assignment (LLM parse error)"}}


def send_email_node(state: AssignmentState) -> dict:
    """Send approval-request email to the approver."""
    sent = False
    try:
        send_approval_email(state["ticket"], state["proposed_user"])
        sent = True
    except Exception as exc:
        # Non-fatal — email failure should not block the HITL flow
        print(f"[email] Warning: {exc}")
    return {"approval_status": "pending", "email_sent": sent}


def await_approval_node(state: AssignmentState) -> dict:
    """
    Pauses the graph here until the human resumes via
    Command(resume={"status": "approved"|"rejected", "reason": "..."}).
    """
    decision = interrupt("Waiting for human approval")
    return {
        "approval_status": decision.get("status", "rejected"),
        "rejection_reason": decision.get("reason", ""),
    }


def apply_node(state: AssignmentState) -> dict:
    """
    Dummy assignment applied — local state only, zero Jira API calls.
    """
    return {"approval_status": "approved"}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route_after_approval(state: AssignmentState) -> str:
    return "apply" if state.get("approval_status") == "approved" else "end"


# ---------------------------------------------------------------------------
# Graph (singleton checkpointer so threads survive Streamlit reruns)
# ---------------------------------------------------------------------------

_checkpointer = MemorySaver()


def build_assignment_graph():
    g = StateGraph(AssignmentState)

    g.add_node("propose", propose_node)
    g.add_node("send_email", send_email_node)
    g.add_node("await_approval", await_approval_node)
    g.add_node("apply", apply_node)

    g.set_entry_point("propose")
    g.add_edge("propose", "send_email")
    g.add_edge("send_email", "await_approval")
    g.add_conditional_edges(
        "await_approval",
        _route_after_approval,
        {"apply": "apply", "end": END},
    )
    g.add_edge("apply", END)

    return g.compile(checkpointer=_checkpointer)


def get_checkpointer() -> MemorySaver:
    return _checkpointer
