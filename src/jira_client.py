"""
Jira REST API v3 client.
Authenticates with email + API token from environment variables.
"""

import os
import requests
from requests.auth import HTTPBasicAuth

JIRA_BASE_URL = os.environ["JIRA_BASE_URL"].rstrip("/")   # e.g. https://netradyne.atlassian.net
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]

_AUTH = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
_HEADERS = {"Accept": "application/json"}


def fetch_dashboard_context(dashboard_id: str) -> dict:
    """
    Resolve a Jira dashboard into a usable JQL scope.

    Strategy (each step falls back to the next if unavailable):
      1. Fetch gadgets on the dashboard.
      2. For each gadget, query its property keys, then each property value;
         extract any filterId reference.
      3. For each filter found, retrieve its saved JQL.
      4. Return the dashboard name + list of JQL fragments.

    If no filters can be resolved the caller falls back to an unscoped query.
    """
    dashboard = _get(f"/rest/api/3/dashboard/{dashboard_id}")
    name = dashboard.get("name", f"Dashboard {dashboard_id}")

    gadgets = _get(f"/rest/api/3/dashboard/{dashboard_id}/gadget").get("gadgets", [])

    filter_ids: list[str] = []
    for gadget in gadgets:
        gid = gadget.get("id")
        if not gid:
            continue
        try:
            prop_keys = _get(
                f"/rest/api/3/dashboard/{dashboard_id}/gadget/{gid}/properties"
            ).get("keys", [])
            for key_obj in prop_keys:
                key = key_obj.get("key", "")
                try:
                    value = _get(
                        f"/rest/api/3/dashboard/{dashboard_id}/gadget/{gid}/properties/{key}"
                    ).get("value", {})
                    # gadget properties store filterId either directly or nested
                    fid = (
                        value.get("filterId")
                        or value.get("filter_id")
                        or value.get("filterId", {}) if isinstance(value, dict) else None
                    )
                    if fid and str(fid) not in filter_ids:
                        filter_ids.append(str(fid))
                except Exception:
                    pass
        except Exception:
            pass

    jql_fragments: list[str] = []
    for fid in filter_ids:
        try:
            f = _get(f"/rest/api/3/filter/{fid}")
            jql = f.get("jql", "").strip()
            if jql:
                jql_fragments.append(jql)
        except Exception:
            pass

    return {"name": name, "filter_ids": filter_ids, "jql_fragments": jql_fragments}


def fetch_todays_tickets(
    project_key: str | None = None,
    dashboard_context: dict | None = None,
) -> list[dict]:
    """
    Return all tickets created during the previous calendar day.

    Scope priority:
      1. Dashboard filter JQL  (if dashboard_context has jql_fragments)
      2. project_key           (if provided)
      3. Whole instance        (fallback)
    """
    last_7d = "created >= -7d"

    if dashboard_context and dashboard_context.get("jql_fragments"):
        base = " OR ".join(f"({q})" for q in dashboard_context["jql_fragments"])
        jql = f"({base}) AND {last_7d} ORDER BY created DESC"
    elif project_key:
        jql = f"project = {project_key} AND {last_7d} ORDER BY created DESC"
    else:
        jql = f"{last_7d} ORDER BY created DESC"

    return _search(jql, fields="summary,description,priority,status,created,assignee,issuetype")


def fetch_resolved_tickets(
    project_key: str | None = None,
    dashboard_context: dict | None = None,
    max_results: int = 1000,
) -> list[dict]:
    """Return resolved/done tickets for embedding & indexing into Pinecone."""
    resolved = "status in (Resolved, Done, Closed) AND resolution is not EMPTY"

    if dashboard_context and dashboard_context.get("jql_fragments"):
        base = " OR ".join(f"({q})" for q in dashboard_context["jql_fragments"])
        jql = f"({base}) AND {resolved} ORDER BY updated DESC"
    elif project_key:
        jql = f"project = {project_key} AND {resolved} ORDER BY updated DESC"
    else:
        jql = f"{resolved} ORDER BY updated DESC"

    return _search(
        jql,
        fields="summary,description,priority,status,resolution,resolutiondate,assignee",
        max_results=max_results,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(path: str) -> dict:
    """GET a Jira REST API path, return parsed JSON dict."""
    url = f"{JIRA_BASE_URL}{path}"
    resp = requests.get(url, headers=_HEADERS, auth=_AUTH, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _search(jql: str, fields: str, max_results: int = 100) -> list[dict]:
    """
    Paginate through Jira search results using the current Cloud endpoint.
    Uses POST /rest/api/3/search/jql (replaces the deprecated GET /search).
    """
    PAGE_SIZE = 50
    field_list = [f.strip() for f in fields.split(",")]
    collected: list[dict] = []
    next_page_token: str | None = None

    while len(collected) < max_results:
        want = min(PAGE_SIZE, max_results - len(collected))
        payload: dict = {"jql": jql, "maxResults": want, "fields": field_list}
        if next_page_token:
            payload["nextPageToken"] = next_page_token

        url = f"{JIRA_BASE_URL}/rest/api/3/search/jql"
        resp = requests.post(
            url,
            headers={**_HEADERS, "Content-Type": "application/json"},
            auth=_AUTH,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        page = body.get("issues", [])
        if not page:
            break
        collected.extend(_normalise(issue) for issue in page)
        next_page_token = body.get("nextPageToken")
        if not next_page_token:
            break

    return collected


def _normalise(issue: dict) -> dict:
    f = issue["fields"]
    return {
        "id": issue["id"],
        "key": issue["key"],
        "summary": f.get("summary") or "",
        "description": _adf_to_text(f.get("description")),
        "priority": (f.get("priority") or {}).get("name", "Unknown"),
        "status": (f.get("status") or {}).get("name", "Unknown"),
        "issue_type": (f.get("issuetype") or {}).get("name", ""),
        "assignee": (f.get("assignee") or {}).get("displayName", "Unassigned"),
        "created": f.get("created", ""),
        "resolution": (f.get("resolution") or {}).get("name", ""),
        "resolution_date": f.get("resolutiondate") or "",
    }


def _adf_to_text(node) -> str:
    """Recursively extract plain text from Atlassian Document Format (ADF) JSON."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    return " ".join(_adf_to_text(child) for child in node.get("content", [])).strip()
