from typing import TypedDict, Optional


class AgentState(TypedDict):
    # Input
    project_key: Optional[str]
    dashboard_id: Optional[str]          # e.g. "12042"

    # Resolved dashboard metadata (name + filter JQL fragments)
    dashboard_context: Optional[dict]

    # Fetched from Jira
    todays_tickets: list[dict]

    # Grouped by priority (Blocker → Critical → Major → ...)
    grouped_tickets: dict[str, list[dict]]

    # Each ticket paired with its semantically similar resolved tickets
    tickets_with_similar: list[dict]

    # Final LLM-generated triage report
    report: str

    # Non-empty if any node failed
    error: Optional[str]
