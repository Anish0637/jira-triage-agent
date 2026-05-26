"""
HTML email notifier via SMTP (no Slack dependency).
Sends assignment approval requests to the configured approver.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
APPROVER_EMAIL = os.getenv("APPROVER_EMAIL", "anish.kumar@netradyne.com")
STREAMLIT_URL = os.getenv("STREAMLIT_URL", "http://localhost:8501")

PRIORITY_EMOJI = {
    "Highest": "🔴", "Blocker": "🔴", "Critical": "🔴",
    "High": "🟠", "Major": "🟠",
    "Medium": "🟡",
    "Minor": "🟢", "Low": "🟢", "Trivial": "⚪",
}


def send_approval_email(ticket: dict, proposed_user: dict) -> None:
    """
    Send an HTML approval-request email to APPROVER_EMAIL.
    Raises if SMTP credentials are not configured.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP_USER and SMTP_PASSWORD must be set in .env to send emails."
        )

    priority_icon = PRIORITY_EMOJI.get(ticket.get("priority", ""), "")
    jira_url = f"https://netradyne.atlassian.net/browse/{ticket['key']}"
    approvals_url = f"{STREAMLIT_URL}?tab=approvals"

    subject = (
        f"[Triage Approval Needed] {ticket['key']} → {proposed_user['name']}"
    )

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">

  <h2 style="color:#1a73e8">🎫 Jira Triage — Assignment Approval Required</h2>

  <table style="border-collapse:collapse;width:100%;margin-bottom:20px">
    <tr style="background:#f5f5f5">
      <td style="padding:10px;border:1px solid #ddd;width:140px"><b>Ticket</b></td>
      <td style="padding:10px;border:1px solid #ddd">
        <a href="{jira_url}" style="color:#1a73e8">{ticket['key']}</a>
      </td>
    </tr>
    <tr>
      <td style="padding:10px;border:1px solid #ddd"><b>Summary</b></td>
      <td style="padding:10px;border:1px solid #ddd">{ticket['summary']}</td>
    </tr>
    <tr style="background:#f5f5f5">
      <td style="padding:10px;border:1px solid #ddd"><b>Priority</b></td>
      <td style="padding:10px;border:1px solid #ddd">
        {priority_icon} {ticket.get('priority', 'Unknown')}
      </td>
    </tr>
    <tr>
      <td style="padding:10px;border:1px solid #ddd"><b>Proposed Assignee</b></td>
      <td style="padding:10px;border:1px solid #ddd">
        <b>{proposed_user['name']}</b> — {proposed_user['role']}
      </td>
    </tr>
    <tr style="background:#f5f5f5">
      <td style="padding:10px;border:1px solid #ddd"><b>Reason</b></td>
      <td style="padding:10px;border:1px solid #ddd">
        {proposed_user.get('reason', 'Best match for ticket type')}
      </td>
    </tr>
  </table>

  <div style="background:#fff8e1;border-left:4px solid #ffc107;padding:12px;margin-bottom:20px">
    ⚠️ <b>This is a dummy assignment only.</b>
    No changes will be made in Jira.
  </div>

  <p>To <b>Approve or Reject</b>, open the Triage Dashboard and go to the
  <b>Pending Approvals</b> tab:</p>

  <a href="{approvals_url}"
     style="display:inline-block;background:#1a73e8;color:white;
            padding:12px 24px;text-decoration:none;border-radius:6px;
            font-weight:bold">
    Open Pending Approvals →
  </a>

  <p style="color:#888;font-size:12px;margin-top:30px">
    Sent by the Jira LangGraph Triage Agent
  </p>
</body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = APPROVER_EMAIL
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, APPROVER_EMAIL, msg.as_string())
