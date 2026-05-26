"""
Streamlit Triage Dashboard
──────────────────────────
Tab 1 — Tickets        : grouped by priority, details, similar resolved, Auto-assign
Tab 2 — Triage Report  : LLM-generated markdown summary
Tab 3 — Pending Approvals : HITL approve / reject with email notification
"""

import uuid
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Jira Triage Dashboard",
    page_icon="🎫",
    layout="wide",
)

PRIORITY_ICON = {
    "Highest": "🔴", "Blocker": "🔴", "Critical": "🔴",
    "High": "🟠", "Major": "🟠",
    "Medium": "🟡",
    "Minor": "🟢", "Low": "🟢", "Trivial": "⚪",
}


# ── Cached singletons (survive Streamlit reruns) ─────────────────────────────

@st.cache_resource
def get_triage_graph():
    from src.graph import build_graph
    return build_graph()


@st.cache_resource
def get_assignment_graph():
    from src.assignment_graph import build_assignment_graph
    return build_assignment_graph()


# ── Session state defaults ────────────────────────────────────────────────────

def _init_state():
    if "triage_result" not in st.session_state:
        st.session_state.triage_result = None
    if "assignments" not in st.session_state:
        # ticket_key → {thread_id, proposed_user, status, ticket, email_sent}
        st.session_state.assignments = {}


_init_state()

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Controls")
    project = st.text_input("Project Key", value="ANOPS")
    st.caption("Dashboard: Analytics-Support-Tickets (#12042)")
    st.caption("Window: last 7 days")
    st.divider()

    run_clicked = st.button("▶ Run Triage", type="primary", use_container_width=True)

    if run_clicked:
        with st.spinner("Running triage agent…"):
            try:
                graph = get_triage_graph()
                result = graph.invoke({
                    "dashboard_id": "12042",
                    "dashboard_context": None,
                    "project_key": project,
                    "todays_tickets": [],
                    "grouped_tickets": {},
                    "tickets_with_similar": [],
                    "report": "",
                    "error": None,
                })
                if result.get("error"):
                    st.error(result["error"])
                else:
                    st.session_state.triage_result = result
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))

    result = st.session_state.triage_result
    if result:
        n = len(result.get("todays_tickets", []))
        st.success(f"✅ {n} ticket(s) loaded")

    pending_count = sum(
        1 for a in st.session_state.assignments.values()
        if a["status"] == "pending"
    )
    if pending_count:
        st.warning(f"⏳ {pending_count} approval(s) pending")

    st.divider()
    st.caption("Dummy assignment — no Jira changes made")

# ── Header ────────────────────────────────────────────────────────────────────

st.title("🎫 Jira Triage Dashboard")
st.caption("Analytics-Support-Tickets · Last 7 days · Dummy assignments only")

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_tickets, tab_report, tab_approvals = st.tabs([
    "📋 Tickets",
    "📊 Triage Report",
    f"✅ Pending Approvals ({pending_count})" if pending_count else "✅ Pending Approvals",
])

result = st.session_state.triage_result

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — TICKETS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_tickets:
    if not result:
        st.info("Click **▶ Run Triage** in the sidebar to fetch tickets.")
        st.stop()

    similar_map = {
        item["ticket"]["key"]: item["similar_resolved"]
        for item in result.get("tickets_with_similar", [])
    }

    grouped = result.get("grouped_tickets", {})
    if not grouped:
        st.warning("No tickets found in the last 7 days.")
    else:
        # Summary metrics row
        cols = st.columns(len(grouped))
        for col, (priority, tickets) in zip(cols, grouped.items()):
            icon = PRIORITY_ICON.get(priority, "⚪")
            col.metric(f"{icon} {priority}", len(tickets))

        st.divider()

        for priority, tickets in grouped.items():
            icon = PRIORITY_ICON.get(priority, "⚪")
            st.subheader(f"{icon} {priority} — {len(tickets)} ticket(s)")

            for t in tickets:
                key = t["key"]
                assignment = st.session_state.assignments.get(key)

                label = f"**[{key}]** {t['summary']}"
                with st.expander(label, expanded=(priority in ("Highest", "Blocker", "Critical"))):

                    # ── Ticket metadata ─────────────────────────────────────
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Priority", t["priority"])
                    c2.metric("Status", t["status"])
                    c3.metric("Type", t.get("issue_type", "—"))
                    c4.metric("Assignee", t.get("assignee", "Unassigned"))

                    desc = t.get("description", "").strip()
                    if desc:
                        with st.container():
                            st.markdown("**Description**")
                            st.text(desc[:600] + ("…" if len(desc) > 600 else ""))

                    # ── Similar resolved tickets ────────────────────────────
                    similar = similar_map.get(key, [])
                    st.markdown("**Similar resolved tickets**")
                    if similar:
                        rows = [
                            {
                                "Key": s["key"],
                                "Summary": s["summary"][:90],
                                "Score": s["score"],
                                "Resolution": s["resolution"],
                                "Resolved": s.get("resolution_date", "")[:10],
                            }
                            for s in similar
                        ]
                        st.dataframe(rows, use_container_width=True, hide_index=True)
                    else:
                        st.caption("No similar resolved tickets found.")

                    st.divider()

                    # ── Assignment widget ───────────────────────────────────
                    if assignment:
                        s = assignment["status"]
                        user = assignment["proposed_user"]
                        if s == "pending":
                            st.warning(
                                f"⏳ Awaiting approval — proposed: **{user['name']}** "
                                f"({user['role']})\n\n"
                                f"_{user.get('reason', '')}_"
                            )
                            if assignment.get("email_sent"):
                                st.caption("📧 Approval email sent to anish.kumar@netradyne.com")
                            else:
                                st.caption("⚠️ Email not sent (check SMTP config). Approve in **Pending Approvals** tab.")
                        elif s == "approved":
                            st.success(
                                f"✅ Assigned (dummy) to **{user['name']}** — {user['role']}\n\n"
                                f"_{user.get('reason', '')}_"
                            )
                        elif s == "rejected":
                            reason = assignment.get("rejection_reason", "")
                            st.error(f"❌ Rejected. {reason}")
                            if st.button("↩ Re-assign", key=f"retry_{key}"):
                                del st.session_state.assignments[key]
                                st.rerun()
                    else:
                        if st.button(
                            "🤖 Auto-assign (dummy)",
                            key=f"assign_{key}",
                            type="secondary",
                        ):
                            with st.spinner(f"Proposing assignment for {key}…"):
                                try:
                                    ag = get_assignment_graph()
                                    thread_id = str(uuid.uuid4())
                                    config = {"configurable": {"thread_id": thread_id}}

                                    ag.invoke(
                                        {
                                            "ticket": t,
                                            "proposed_user": None,
                                            "approval_status": None,
                                            "rejection_reason": None,
                                            "email_sent": False,
                                        },
                                        config,
                                    )

                                    # Read state after interrupt
                                    snap = ag.get_state(config)
                                    proposed = snap.values.get("proposed_user") or {}
                                    email_sent = snap.values.get("email_sent", False)

                                    st.session_state.assignments[key] = {
                                        "thread_id": thread_id,
                                        "proposed_user": proposed,
                                        "status": "pending",
                                        "ticket": t,
                                        "email_sent": email_sent,
                                    }
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Assignment failed: {exc}")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — TRIAGE REPORT
# ═══════════════════════════════════════════════════════════════════════════════

with tab_report:
    if not result:
        st.info("Run triage first.")
    elif not result.get("report"):
        st.warning("No report was generated.")
    else:
        ctx = result.get("dashboard_context") or {}
        if ctx.get("name"):
            st.caption(f"Dashboard: {ctx['name']}")
        st.markdown(result["report"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PENDING APPROVALS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_approvals:
    pending_items = [
        (k, v)
        for k, v in st.session_state.assignments.items()
        if v["status"] == "pending"
    ]

    if not pending_items:
        st.success("No pending approvals — inbox is clear. ✓")
    else:
        st.info(
            f"**{len(pending_items)} assignment(s) awaiting approval.** "
            "Review each and click Approve or Reject."
        )

        for ticket_key, assignment in pending_items:
            user = assignment["proposed_user"]
            ticket = assignment["ticket"]
            icon = PRIORITY_ICON.get(ticket.get("priority", ""), "⚪")

            with st.container(border=True):
                left, right = st.columns([3, 1])

                with left:
                    st.markdown(
                        f"### {icon} [{ticket_key}]  {ticket['summary']}"
                    )
                    st.markdown(
                        f"**Priority:** {ticket['priority']} &nbsp;|&nbsp; "
                        f"**Status:** {ticket['status']}"
                    )
                    st.markdown(
                        f"**Proposed assignee:** {user['name']} "
                        f"*(dummy — {user['role']})*"
                    )
                    st.markdown(f"**Reason:** _{user.get('reason', '—')}_")
                    if assignment.get("email_sent"):
                        st.caption("📧 Email notification sent")

                with right:
                    st.write("")  # spacer
                    approve = st.button(
                        "✅ Approve",
                        key=f"approve_{ticket_key}",
                        type="primary",
                        use_container_width=True,
                    )
                    reject_reason = st.text_input(
                        "Rejection reason",
                        placeholder="Optional…",
                        key=f"reason_{ticket_key}",
                        label_visibility="collapsed",
                    )
                    reject = st.button(
                        "❌ Reject",
                        key=f"reject_{ticket_key}",
                        use_container_width=True,
                    )

                if approve:
                    from langgraph.types import Command
                    ag = get_assignment_graph()
                    ag.invoke(
                        Command(resume={"status": "approved"}),
                        {"configurable": {"thread_id": assignment["thread_id"]}},
                    )
                    st.session_state.assignments[ticket_key]["status"] = "approved"
                    st.rerun()

                if reject:
                    from langgraph.types import Command
                    ag = get_assignment_graph()
                    ag.invoke(
                        Command(resume={"status": "rejected", "reason": reject_reason}),
                        {"configurable": {"thread_id": assignment["thread_id"]}},
                    )
                    st.session_state.assignments[ticket_key]["status"] = "rejected"
                    st.session_state.assignments[ticket_key]["rejection_reason"] = reject_reason
                    st.rerun()
