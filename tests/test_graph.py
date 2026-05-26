"""
End-to-end graph tests — verifies full LangGraph pipeline
with all external I/O mocked at the node boundary.
"""

from unittest.mock import patch, MagicMock
import pytest

from tests.test_nodes import TODAY_TICKETS, SIMILAR_RESOLVED

def _base_state():
    return {
        "dashboard_id": "12042",
        "dashboard_context": None,
        "project_key": "NET",
        "todays_tickets": [],
        "grouped_tickets": {},
        "tickets_with_similar": [],
        "report": "",
        "error": None,
    }


class TestFullGraph:

    def test_happy_path(self):
        from src.graph import build_graph

        mock_report = MagicMock()
        mock_report.content = "Triage report: 3 tickets today."
        mock_ctx = {"name": "Netradyne Dashboard", "filter_ids": ["555"], "jql_fragments": ["project = NET"]}

        with patch("src.nodes.fetch_dashboard_context", return_value=mock_ctx), \
             patch("src.nodes.fetch_todays_tickets", return_value=TODAY_TICKETS), \
             patch("src.nodes.find_similar", return_value=SIMILAR_RESOLVED), \
             patch("src.nodes._llm") as mock_llm:

            mock_llm.invoke.return_value = mock_report
            graph = build_graph()
            final = graph.invoke(_base_state())

        assert final["error"] is None
        assert len(final["todays_tickets"]) == 3
        assert "Blocker" in final["grouped_tickets"]
        assert len(final["tickets_with_similar"]) == 3
        assert final["report"] == mock_report.content
        assert final["dashboard_context"]["name"] == "Netradyne Dashboard"

    def test_no_tickets_today_skips_to_end(self):
        from src.graph import build_graph

        with patch("src.nodes.fetch_dashboard_context", return_value={"name": "D", "filter_ids": [], "jql_fragments": []}), \
             patch("src.nodes.fetch_todays_tickets", return_value=[]), \
             patch("src.nodes.find_similar") as mock_sim, \
             patch("src.nodes._llm") as mock_llm:

            graph = build_graph()
            final = graph.invoke(_base_state())

        mock_sim.assert_not_called()
        mock_llm.invoke.assert_not_called()
        assert final["todays_tickets"] == []
        assert final["report"] == ""

    def test_jira_error_skips_to_end(self):
        from src.graph import build_graph

        with patch("src.nodes.fetch_dashboard_context", side_effect=Exception("Connection refused")), \
             patch("src.nodes.find_similar") as mock_sim, \
             patch("src.nodes._llm") as mock_llm:

            graph = build_graph()
            final = graph.invoke(_base_state())

        assert "Connection refused" in final["error"]
        mock_sim.assert_not_called()
        mock_llm.invoke.assert_not_called()

    def test_severity_grouping_preserved_end_to_end(self):
        from src.graph import build_graph

        mock_report = MagicMock()
        mock_report.content = "ok"

        with patch("src.nodes.fetch_dashboard_context", return_value={"name": "D", "filter_ids": [], "jql_fragments": []}), \
             patch("src.nodes.fetch_todays_tickets", return_value=TODAY_TICKETS), \
             patch("src.nodes.find_similar", return_value=[]), \
             patch("src.nodes._llm") as mock_llm:

            mock_llm.invoke.return_value = mock_report
            graph = build_graph()
            final = graph.invoke(_base_state())

        keys = list(final["grouped_tickets"].keys())
        assert keys.index("Blocker") < keys.index("Major")
        assert keys.index("Major") < keys.index("Minor")
