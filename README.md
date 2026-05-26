# Jira LangGraph Triage Agent

AI-powered triage system for Jira tickets. Fetches tickets from the last 7 days, groups them by severity, finds semantically similar resolved tickets via Pinecone, generates a GPT-4o triage report, and provides a Streamlit dashboard with a human-in-the-loop (HITL) dummy-assignment workflow.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Streamlit Dashboard                          │
│   Tab 1: Tickets  │  Tab 2: Triage Report  │  Tab 3: Approvals  │
└──────────┬──────────────────────────────────────────┬───────────┘
           │ Run Triage                               │ Approve / Reject
           ▼                                          ▼
┌─────────────────────┐              ┌──────────────────────────────┐
│  Triage LangGraph   │              │   Assignment HITL LangGraph   │
│                     │              │                              │
│  fetch_tickets      │              │  propose  (GPT-4o picks      │
│       ↓             │              │  best dummy user)            │
│  group_by_priority  │              │       ↓                      │
│       ↓             │              │  send_email  (Office 365)    │
│  find_similar       │              │       ↓                      │
│  (Pinecone search)  │              │  await_approval  ← interrupt │
│       ↓             │              │       ↓                      │
│  generate_report    │              │  apply  (local state only,   │
│  (GPT-4o)           │              │  zero Jira API calls)        │
└─────────────────────┘              └──────────────────────────────┘
           │                                          │
           ▼                                          ▼
    Jira REST API v3              Email → approver@your-company.com
    Pinecone Vector DB            MemorySaver (thread checkpointing)
    OpenAI Embeddings
```

---

## Project Structure

```
jira-langgraph-agent/
├── streamlit_app.py          # Streamlit dashboard (3 tabs)
├── main.py                   # CLI entrypoint
├── requirements.txt
├── .env                      # Credentials (never commit)
├── .env.example              # Template
│
└── src/
    ├── state.py              # AgentState TypedDict
    ├── jira_client.py        # Jira REST API v3 (paginated, POST /search/jql)
    ├── pinecone_store.py     # Embed + upsert + query resolved tickets
    ├── nodes.py              # LangGraph node functions
    ├── graph.py              # Triage graph wiring
    ├── dummy_users.py        # 5 dummy assignees (no real Jira users)
    ├── email_notifier.py     # SMTP HTML email via Office 365
    └── assignment_graph.py   # HITL assignment LangGraph
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Fill in all values — see table below
```

| Variable | Description |
|---|---|
| `JIRA_BASE_URL` | `https://your-org.atlassian.net` |
| `JIRA_EMAIL` | Your Atlassian login email |
| `JIRA_API_TOKEN` | From [id.atlassian.com → Security → API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `JIRA_DASHBOARD_ID` | `12042` |
| `OPENAI_API_KEY` | From [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `PINECONE_API_KEY` | From [app.pinecone.io](https://app.pinecone.io) |
| `PINECONE_INDEX_NAME` | `jira-resolved-tickets` (auto-created) |
| `SMTP_HOST` | `smtp.office365.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Sender email address |
| `SMTP_PASSWORD` | Office 365 App Password (not your login password) |
| `APPROVER_EMAIL` | `approver@your-company.com` |
| `STREAMLIT_URL` | `http://localhost:8502` |

### 3. Index resolved tickets (one-time)

Embeds all resolved ANOPS tickets into Pinecone for semantic search.

```bash
python3 main.py --index-resolved --project ANOPS
```

Re-run weekly (or as a cron) to keep the index fresh.

---

## Running

### Streamlit Dashboard (recommended)

```bash
python3 -m streamlit run streamlit_app.py --server.port 8502
```

Open **http://localhost:8502** in your browser.

### CLI (headless)

```bash
python3 main.py --project ANOPS
```

---

## Triage Flow (step by step)

```
1. User clicks "▶ Run Triage" in sidebar
        │
        ▼
2. fetch_tickets_node
   • Calls GET /rest/api/3/dashboard/12042 → resolves dashboard name
   • Tries to extract gadget filter JQL (falls back gracefully if unavailable)
   • Queries Jira: project = ANOPS AND created >= -7d
        │
        ▼
3. group_by_priority_node
   • Sorts tickets: Highest → Blocker → Critical → High → Major → Medium → Minor → Low → Trivial
        │
        ▼
4. find_similar_node
   • Embeds each ticket's summary + description (text-embedding-3-small)
   • Queries Pinecone top-3 cosine matches from the resolved-tickets namespace
   • Attaches similar tickets with similarity scores to each new ticket
        │
        ▼
5. generate_report_node
   • GPT-4o generates a Slack-ready triage report:
     - Total count by priority
     - Blocker/Critical tickets called out explicitly
     - Tickets with score ≥ 0.80 flagged to review resolved resolution
     - 3–5 prioritised next actions for the on-call team
        │
        ▼
6. Results displayed in Streamlit (Tab 1 + Tab 2)
```

---

## HITL Assignment Flow (step by step)

```
1. User clicks "🤖 Auto-assign (dummy)" on a ticket
        │
        ▼
2. propose_node  (LangGraph)
   • GPT-4o reads ticket summary, description, and priority
   • Picks the best dummy user from the team roster
   • Returns: user + one-sentence reason
        │
        ▼
3. send_email_node
   • Sends HTML email to APPROVER_EMAIL via Office 365 SMTP
   • Email contains: ticket key, summary, priority, proposed assignee, reason
   • Links back to the Streamlit Pending Approvals tab
   • Non-fatal: if SMTP is not configured, flow continues without email
        │
        ▼
4. await_approval_node  ← interrupt() — graph pauses here
   • Thread ID saved in MemorySaver (survives Streamlit reruns)
   • UI shows "⏳ Awaiting approval" on the ticket card
        │
        ▼
5. User opens Tab 3 (Pending Approvals) → clicks ✅ Approve or ❌ Reject
        │
    ┌───┴───────────────┐
    │ Approve           │ Reject
    ▼                   ▼
6a. apply_node        6b. Graph ends
    • Local state         • Ticket returns to
      marked "assigned"     unassigned
    • ✅ shown on card    • ❌ shown with reason
    • Zero Jira API         + "↩ Re-assign" button
      calls made
```

---

## Dummy Users

| Name | Role | Best for |
|---|---|---|
| Alice Chen | Alert Analysis Engineer | Sign violations, traffic lights, distraction alerts |
| Bob Smith | Device & Hardware Engineer | Camera sync, video, blurred footage |
| Carol Davis | ML / AI Engineer | DMS, drowsy alerts, false positives, model precision |
| David Lee | Customer Support Engineer | Trial customers, seatbelt, collision, in-cab audio |
| Eva Martinez | Data & Analytics Engineer | Alert count anomalies, data investigations |

---

## Notes

- **No real Jira assignments are made.** The `apply_node` only updates in-memory Streamlit session state.
- **Email requires an Office 365 App Password** — your regular login password will be rejected by Microsoft's SMTP relay. Generate one at [mysignins.microsoft.com/security-info](https://mysignins.microsoft.com/security-info).
- **If SMTP is unavailable**, all HITL functionality still works through the Pending Approvals tab only.
- **Pinecone index** must be populated before running triage (`--index-resolved`). Re-run weekly.
- **Dashboard 12042** ("Analytics-Support-Tickets") has no extractable gadget filters via Jira REST API v3 — the agent uses `--project ANOPS` as the scope fallback.
