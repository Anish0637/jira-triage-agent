"""
Unit tests for individual LangGraph nodes.
All external I/O (Jira REST, Pinecone, OpenAI) is mocked.
"""

from unittest.mock import patch, MagicMock
import pytest

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TODAY_TICKETS = [
    {
        "id": "1", "key": "NET-101",
        "summary": "App crashes on login",
        "description": "Users report crash when tapping the login button on iOS 17.",
        "priority": "Blocker", "status": "Open",
        "issue_type": "Bug", "assignee": "Alice",
        "created": "2026-05-26T08:00:00.000+0000",
        "resolution": "", "resolution_date": "",
    },
    {
        "id": "2", "key": "NET-102",
        "summary": "Dashboard loads slowly",
        "description": "Dashboard takes 10+ seconds to load for enterprise accounts.",
        "priority": "Major", "status": "Open",
        "issue_type": "Bug", "assignee": "Bob",
        "created": "2026-05-26T09:00:00.000+0000",
        "resolution": "", "resolution_date": "",
    },
    {
        "id": "3", "key": "NET-103",
        "summary": "Typo in footer",
        "description": "Footer shows 'Copyrigth' instead of 'Copyright'.",
        "priority": "Minor", "status": "Open",
        "issue_type": "Task", "assignee": "Unassigned",
        "created": "2026-05-26T10:00:00.000+0000",
        "resolution": "", "resolution_date": "",
    },
]

SIMILAR_RESOLVED = [
    {
        "key": "NET-50", "summary": "Login crash on iOS 17",
        "priority": "Blocker", "resolution": "Fixed",
        "resolution_date": "2026-05-01", "score": 0.92,
    },
    {
        "key": "NET-75", "summary": "Auth service timeout on login",
        "priority": "Critical", "resolution": "Workaround applied",
        "resolution_date": "2026-04-15", "score": 0.76,
    },
]


# ---------------------------------------------------------------------------
# Node 1: fetch_tickets_node
# ---------------------------------------------------------------------------

class TestFetchTicketsNode:

    def test_success(self):
        with patch("src.nodes.fetch_dashboard_context", return_value={"name": "Test Dash", "filter_ids": [], "jql_fragments": []}) as mock_ctx, \
             patch("src.nodes.fetch_todays_tickets", return_value=TODAY_TICKETS) as mock_fetch:
            from src.nodes import fetch_tickets_node
            state = {"dashboard_id": "12042", "project_key": "NET", "dashboard_context": None,
                     "todays_tickets": [], "grouped_tickets": {},
                     "tickets_with_similar": [], "report": "", "error": None}
            result = fetch_tickets_node(state)

        assert result["error"] is None
        assert result["todays_tickets"] == TODAY_TICKETS
        mock_ctx.assert_called_once_with("12042")
        mock_fetch.assert_called_once()

    def test_jira_api_failure(self):
        with patch("src.nodes.fetch_dashboard_context", return_value=None, side_effect=Exception("401 Unauthorized")):
            from src.nodes import fetch_tickets_node
            state = {"dashboard_id": "12042", "project_key": "NET", "dashboard_context": None,
                     "todays_tickets": [], "grouped_tickets": {},
                     "tickets_with_similar": [], "report": "", "error": None}
            result = fetch_tickets_node(state)

        assert result["todays_tickets"] == []
        assert "401 Unauthorized" in result["error"]

    def test_no_project_key(self):
        with patch("src.nodes.fetch_dashboard_context", return_value={"name": "D", "filter_ids": [], "jql_fragments": []}), \
             patch("src.nodes.fetch_todays_tickets", return_value=[]) as mock_fetch:
            from src.nodes import fetch_tickets_node
            state = {"dashboard_id": None, "project_key": None, "dashboard_context": None,
                     "todays_tickets": [], "grouped_tickets": {},
                     "tickets_with_similar": [], "report": "", "error": None}
            fetch_tickets_node(state)

        mock_fetch.assert_called_once()


# ---------------------------------------------------------------------------
# Node 2: group_by_priority_node
# ---------------------------------------------------------------------------

class TestGroupByPriorityNode:

    def test_correct_grouping(self):
        from src.nodes import group_by_priority_node
        state = {"todays_tickets": TODAY_TICKETS, "grouped_tickets": {}}
        result = group_by_priority_node(state)

        grouped = result["grouped_tickets"]
        assert "Blocker" in grouped
        assert "Major" in grouped
        assert "Minor" in grouped
        assert grouped["Blocker"][0]["key"] == "NET-101"
        assert grouped["Major"][0]["key"] == "NET-102"
        assert grouped["Minor"][0]["key"] == "NET-103"

    def test_priority_order(self):
        """Blocker must come before Major, Major before Minor."""
        from src.nodes import group_by_priority_node
        state = {"todays_tickets": TODAY_TICKETS, "grouped_tickets": {}}
        result = group_by_priority_node(state)

        keys = list(result["grouped_tickets"].keys())
        assert keys.index("Blocker") < keys.index("Major")
        assert keys.index("Major") < keys.index("Minor")

    def test_empty_tickets(self):
        from src.nodes import group_by_priority_node
        state = {"todays_tickets": [], "grouped_tickets": {}}
        result = group_by_priority_node(state)
        assert result["grouped_tickets"] == {}

    def test_unknown_priority_appended_at_end(self):
        from src.nodes import group_by_priority_node
        tickets = TODAY_TICKETS + [{
            **TODAY_TICKETS[0],
            "key": "NET-999",
            "priority": "P0-CustomPriority",
        }]
        state = {"todays_tickets": tickets, "grouped_tickets": {}}
        result = group_by_priority_node(state)

        keys = list(result["grouped_tickets"].keys())
        assert keys[-1] == "P0-CustomPriority"


# ---------------------------------------------------------------------------
# Node 3: find_similar_node
# ---------------------------------------------------------------------------

class TestFindSimilarNode:

    def test_similar_attached_to_each_ticket(self):
        with patch("src.nodes.find_similar", return_value=SIMILAR_RESOLVED):
            from src.nodes import find_similar_node
            state = {
                "todays_tickets": TODAY_TICKETS,
                "tickets_with_similar": [],
            }
            result = find_similar_node(state)

        items = result["tickets_with_similar"]
        assert len(items) == len(TODAY_TICKETS)
        for item in items:
            assert "ticket" in item
            assert "similar_resolved" in item
            assert item["similar_resolved"] == SIMILAR_RESOLVED

    def test_no_similar_found(self):
        with patch("src.nodes.find_similar", return_value=[]):
            from src.nodes import find_similar_node
            state = {"todays_tickets": TODAY_TICKETS[:1], "tickets_with_similar": []}
            result = find_similar_node(state)

        assert result["tickets_with_similar"][0]["similar_resolved"] == []

    def test_top_k_passed_correctly(self):
        with patch("src.nodes.find_similar", return_value=[]) as mock_sim:
            from src.nodes import find_similar_node
            state = {"todays_tickets": TODAY_TICKETS[:1], "tickets_with_similar": []}
            find_similar_node(state)

        mock_sim.assert_called_once_with(TODAY_TICKETS[0], top_k=3)


# ---------------------------------------------------------------------------
# Node 4: generate_report_node
# ---------------------------------------------------------------------------

class TestGenerateReportNode:

    def _make_state(self):
        similar_map = {
            "NET-101": SIMILAR_RESOLVED,
            "NET-102": [],
            "NET-103": [],
        }
        return {
            "grouped_tickets": {
                "Blocker": [TODAY_TICKETS[0]],
                "Major": [TODAY_TICKETS[1]],
                "Minor": [TODAY_TICKETS[2]],
            },
            "tickets_with_similar": [
                {"ticket": t, "similar_resolved": similar_map[t["key"]]}
                for t in TODAY_TICKETS
            ],
            "report": "",
        }

    def test_report_generated(self):
        mock_response = MagicMock()
        mock_response.content = "**Triage Report**: 3 tickets today. NET-101 is a Blocker — see NET-50."

        with patch("src.nodes._llm") as mock_llm:
            mock_llm.invoke.return_value = mock_response
            from src.nodes import generate_report_node
            result = generate_report_node(self._make_state())

        assert result["report"] == mock_response.content
        mock_llm.invoke.assert_called_once()

    def test_llm_prompt_contains_ticket_keys(self):
        mock_response = MagicMock()
        mock_response.content = "report text"
        captured_prompt = {}

        def capture_invoke(messages):
            captured_prompt["text"] = messages[0].content
            return mock_response

        with patch("src.nodes._llm") as mock_llm:
            mock_llm.invoke.side_effect = capture_invoke
            from src.nodes import generate_report_node
            generate_report_node(self._make_state())

        prompt_text = captured_prompt["text"]
        assert "NET-101" in prompt_text
        assert "NET-102" in prompt_text
        assert "Blocker" in prompt_text
