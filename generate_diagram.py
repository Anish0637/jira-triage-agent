"""Generate flow diagram as PNG."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

fig, axes = plt.subplots(1, 2, figsize=(20, 16))
fig.patch.set_facecolor("#0f1117")

C = {
    "bg":     "#0f1117",
    "ui":     "#E65100",    # orange  — Streamlit UI
    "node":   "#1565C0",    # blue    — triage nodes
    "hitl":   "#6A1B9A",    # purple  — HITL nodes
    "infra":  "#1B5E20",    # green   — infra / external
    "wait":   "#F57F17",    # amber   — interrupt / human
    "ok":     "#2E7D32",    # dark green — approve
    "no":     "#B71C1C",    # dark red   — reject
    "end":    "#37474F",    # grey    — END
    "text":   "#FFFFFF",
    "sub":    "#B0BEC5",
    "line":   "#78909C",
}


def draw_box(ax, cx, cy, w, h, title, subtitle="", color="#1565C0", shape="rect"):
    if shape == "diamond":
        dx, dy = w / 2, h / 2
        diamond = plt.Polygon(
            [[cx, cy + dy], [cx + dx, cy], [cx, cy - dy], [cx - dx, cy]],
            closed=True, facecolor=color + "33", edgecolor=color, linewidth=2, zorder=3,
        )
        ax.add_patch(diamond)
    else:
        rect = FancyBboxPatch(
            (cx - w / 2, cy - h / 2), w, h,
            boxstyle="round,pad=0.01,rounding_size=0.025",
            facecolor=color + "2A", edgecolor=color, linewidth=2, zorder=3,
        )
        ax.add_patch(rect)

    offset = 0.018 if subtitle else 0
    ax.text(cx, cy + offset, title, ha="center", va="center",
            fontsize=9.5, color=C["text"], fontweight="bold", zorder=4)
    if subtitle:
        ax.text(cx, cy - 0.022, subtitle, ha="center", va="center",
                fontsize=7.5, color=C["sub"], zorder=4)


def arrow_down(ax, cx, y_from, y_to, color="#78909C", label=""):
    ax.annotate("", xy=(cx, y_to), xytext=(cx, y_from),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.8,
                                mutation_scale=16), zorder=2)
    if label:
        ax.text(cx + 0.025, (y_from + y_to) / 2, label,
                fontsize=8, color=color, va="center")


def arrow_branch(ax, cx, y, x_end, y_end, color, label=""):
    ax.annotate("", xy=(x_end, y_end), xytext=(cx, y),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.8,
                                mutation_scale=16,
                                connectionstyle="arc3,rad=0.0"), zorder=2)
    if label:
        mx = (cx + x_end) / 2
        my = (y + y_end) / 2
        ax.text(mx, my + 0.015, label, ha="center", fontsize=8,
                color=color, fontweight="bold")


def side_note(ax, cx, cy, text, color):
    ax.text(cx, cy, text, ha="center", va="center", fontsize=8,
            color=color, style="italic",
            bbox=dict(boxstyle="round,pad=0.25", facecolor=color + "18",
                      edgecolor=color + "88", linewidth=1))


# ─────────────────────────────────────────────────────────────────────────────
# LEFT — Triage flow
# ─────────────────────────────────────────────────────────────────────────────
ax = axes[0]
ax.set_facecolor(C["bg"])
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
ax.set_title("Triage Pipeline", color=C["text"], fontsize=14,
             fontweight="bold", pad=14)

steps_l = [
    (0.5, 0.935, 0.62, 0.075, "Streamlit Dashboard",
     "User clicks  [Run Triage]", C["ui"]),

    (0.5, 0.810, 0.68, 0.085, "fetch_tickets_node",
     "POST /rest/api/3/search/jql\nproject=ANOPS  AND  created >= -7d", C["node"]),

    (0.5, 0.685, 0.68, 0.085, "group_by_priority_node",
     "Sort: Highest > Blocker > Critical\n> High > Major > Medium > Minor", C["node"]),

    (0.5, 0.555, 0.68, 0.090, "find_similar_node",
     "Embed summary+description\nPinecone cosine search  top-3", C["node"]),

    (0.5, 0.420, 0.68, 0.085, "generate_report_node",
     "GPT-4o  *  Slack-ready triage report\nBlockers flagged  *  score >= 0.80 matched", C["node"]),

    (0.5, 0.285, 0.68, 0.085, "Streamlit  --  Tab 1: Tickets",
     "Priority cards  *  details  *  similar resolved table\n[Auto-assign] button per ticket", C["ui"]),

    (0.5, 0.160, 0.68, 0.085, "Streamlit  --  Tab 2: Triage Report",
     "GPT-4o markdown rendered\nPriority breakdown  *  next actions", C["ui"]),
]

for (cx, cy, w, h, title, sub, col) in steps_l:
    draw_box(ax, cx, cy, w, h, title, sub, col)

# Arrows
gaps = [(0.935, 0.810), (0.810, 0.685), (0.685, 0.555),
        (0.555, 0.420), (0.420, 0.285), (0.285, 0.160)]
for (ya, yb) in gaps:
    arrow_down(ax, 0.5, ya - 0.038, yb + 0.043)

# Side infra notes
side_note(ax, 0.88, 0.810, "Jira Cloud\nREST API v3\ndashboard 12042", C["infra"])
side_note(ax, 0.88, 0.555, "Pinecone\ntext-embedding\n-3-small\n270 tickets", C["infra"])
side_note(ax, 0.88, 0.420, "OpenAI\nGPT-4o", C["node"])

ax.annotate("", xy=(0.785, 0.810), xytext=(0.855, 0.810),
            arrowprops=dict(arrowstyle="-|>", color=C["infra"], lw=1.2,
                            linestyle="dashed", mutation_scale=11))
ax.annotate("", xy=(0.840, 0.555), xytext=(0.855, 0.555),
            arrowprops=dict(arrowstyle="-|>", color=C["infra"], lw=1.2,
                            linestyle="dashed", mutation_scale=11))
ax.annotate("", xy=(0.840, 0.420), xytext=(0.855, 0.420),
            arrowprops=dict(arrowstyle="-|>", color=C["node"], lw=1.2,
                            linestyle="dashed", mutation_scale=11))

# END
draw_box(ax, 0.5, 0.060, 0.28, 0.065, "END", "", C["end"])
arrow_down(ax, 0.5, 0.117, 0.093)

# ─────────────────────────────────────────────────────────────────────────────
# RIGHT — HITL Assignment flow
# ─────────────────────────────────────────────────────────────────────────────
ax = axes[1]
ax.set_facecolor(C["bg"])
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
ax.set_title("HITL Assignment Flow", color=C["text"], fontsize=14,
             fontweight="bold", pad=14)

# Steps
draw_box(ax, 0.5, 0.935, 0.64, 0.075,
         "User clicks [Auto-assign]",
         "Streamlit Tab 1  *  ticket passed to graph", C["ui"])

draw_box(ax, 0.5, 0.820, 0.64, 0.085,
         "propose_node",
         "GPT-4o reads ticket type + priority\nPicks best dummy user + reason", C["hitl"])

draw_box(ax, 0.5, 0.700, 0.64, 0.085,
         "send_email_node",
         "HTML email to anish.kumar@netradyne.com\nOffice 365  smtp.office365.com:587", C["hitl"])

draw_box(ax, 0.5, 0.575, 0.64, 0.090,
         "await_approval_node",
         "interrupt()  --  graph paused\nthread saved to MemorySaver", C["wait"])

# Arrows to await
arrow_down(ax, 0.5, 0.897, 0.862)
arrow_down(ax, 0.5, 0.777, 0.742)
arrow_down(ax, 0.5, 0.657, 0.620)

# Human decision diamond
draw_box(ax, 0.5, 0.450, 0.50, 0.080,
         "Approver opens Tab 3",
         "Pending Approvals  *  sees ticket + user + reason", C["wait"],
         shape="rect")
arrow_down(ax, 0.5, 0.530, 0.490)

# Decision diamond
draw_box(ax, 0.5, 0.358, 0.36, 0.072,
         "Approve / Reject ?", "", C["wait"], shape="diamond")
arrow_down(ax, 0.5, 0.410, 0.394)

# Approve branch (left)
ax.plot([0.5, 0.24], [0.358, 0.358], color=C["ok"], lw=1.8)
ax.annotate("", xy=(0.24, 0.270), xytext=(0.24, 0.358),
            arrowprops=dict(arrowstyle="-|>", color=C["ok"], lw=1.8,
                            mutation_scale=15))
ax.text(0.32, 0.363, "APPROVE", fontsize=8, color=C["ok"], fontweight="bold")

draw_box(ax, 0.24, 0.215, 0.38, 0.090,
         "apply_node",
         "Local state  ->  'assigned (dummy)'\nZero Jira API calls made", C["ok"])

# Reject branch (right)
ax.plot([0.5, 0.76], [0.358, 0.358], color=C["no"], lw=1.8)
ax.annotate("", xy=(0.76, 0.270), xytext=(0.76, 0.358),
            arrowprops=dict(arrowstyle="-|>", color=C["no"], lw=1.8,
                            mutation_scale=15))
ax.text(0.60, 0.363, "REJECT", fontsize=8, color=C["no"], fontweight="bold")

draw_box(ax, 0.76, 0.215, 0.38, 0.090,
         "END  (rejected)",
         "Rejection shown on ticket card\n[Re-assign] button appears", C["no"])

# Both converge to final outcome
ax.plot([0.24, 0.24], [0.170, 0.100], color=C["ok"], lw=1.8)
ax.plot([0.76, 0.76], [0.170, 0.100], color=C["no"], lw=1.8)
ax.plot([0.24, 0.76], [0.100, 0.100], color=C["line"], lw=1.8)
ax.annotate("", xy=(0.5, 0.068), xytext=(0.5, 0.100),
            arrowprops=dict(arrowstyle="-|>", color=C["line"], lw=1.8,
                            mutation_scale=15))

draw_box(ax, 0.5, 0.040, 0.72, 0.055,
         "Streamlit refreshes  --  assignment badge updated on ticket card",
         "", C["ui"])

# Side infra notes
side_note(ax, 0.90, 0.700, "Office 365\nSMTP\n:587", C["infra"])
side_note(ax, 0.90, 0.575, "MemorySaver\nthread\ncheckpoint", C["infra"])

ax.annotate("", xy=(0.820, 0.700), xytext=(0.870, 0.700),
            arrowprops=dict(arrowstyle="-|>", color=C["infra"], lw=1.2,
                            linestyle="dashed", mutation_scale=11))
ax.annotate("", xy=(0.820, 0.575), xytext=(0.870, 0.575),
            arrowprops=dict(arrowstyle="-|>", color=C["infra"], lw=1.2,
                            linestyle="dashed", mutation_scale=11))

# ── Legend ────────────────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(facecolor=C["ui"]   + "44", edgecolor=C["ui"],   label="Streamlit UI"),
    mpatches.Patch(facecolor=C["node"] + "44", edgecolor=C["node"], label="Triage node"),
    mpatches.Patch(facecolor=C["hitl"] + "44", edgecolor=C["hitl"], label="HITL node"),
    mpatches.Patch(facecolor=C["wait"] + "44", edgecolor=C["wait"], label="Human checkpoint"),
    mpatches.Patch(facecolor=C["infra"]+ "44", edgecolor=C["infra"],label="External service"),
    mpatches.Patch(facecolor=C["ok"]   + "44", edgecolor=C["ok"],   label="Approved path"),
    mpatches.Patch(facecolor=C["no"]   + "44", edgecolor=C["no"],   label="Rejected path"),
]
fig.legend(handles=legend_items, loc="lower center", ncol=7,
           framealpha=0.15, labelcolor="white", fontsize=8.5,
           facecolor="#1e2130", edgecolor="#3a3f5c",
           bbox_to_anchor=(0.5, 0.0))

plt.suptitle("Jira LangGraph Triage Agent  --  Flow Diagram",
             color="white", fontsize=15, fontweight="bold", y=1.005)
plt.tight_layout(rect=[0, 0.04, 1, 1])

out = "/Users/anishkumar/jira-langgraph-agent/architecture.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved: {out}")


import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, axes = plt.subplots(1, 2, figsize=(22, 14))
fig.patch.set_facecolor("#0f1117")

# ── Colour palette ────────────────────────────────────────────────────────────
C = {
    "bg":       "#0f1117",
    "panel":    "#1e2130",
    "border":   "#3a3f5c",
    "triage":   "#1565C0",
    "hitl":     "#6A1B9A",
    "infra":    "#1B5E20",
    "ui":       "#E65100",
    "arrow":    "#90CAF9",
    "text":     "#FFFFFF",
    "subtext":  "#B0BEC5",
    "green":    "#66BB6A",
    "amber":    "#FFA726",
    "red":      "#EF5350",
    "purple":   "#CE93D8",
}

# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def box(ax, x, y, w, h, label, sublabel="", color="#1565C0", text_color="#FFFFFF",
        fontsize=10, radius=0.04):
    rect = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle=f"round,pad=0.01,rounding_size={radius}",
        linewidth=1.5, edgecolor=color, facecolor=color + "33",
        zorder=3,
    )
    ax.add_patch(rect)
    ax.text(x, y + (0.012 if sublabel else 0), label,
            ha="center", va="center", fontsize=fontsize,
            color=text_color, fontweight="bold", zorder=4)
    if sublabel:
        ax.text(x, y - 0.022, sublabel, ha="center", va="center",
                fontsize=7.5, color=C["subtext"], zorder=4)

def arrow(ax, x1, y1, x2, y2, color="#90CAF9", label=""):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=1.6, mutation_scale=14),
                zorder=2)
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + 0.01, my, label, fontsize=7, color=color,
                ha="left", va="center", zorder=5)

def section_label(ax, x, y, text, color):
    ax.text(x, y, text, ha="center", va="center", fontsize=9,
            color=color, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=color + "22",
                      edgecolor=color, linewidth=1))

# ─────────────────────────────────────────────────────────────────────────────
# LEFT PANEL — Triage LangGraph
# ─────────────────────────────────────────────────────────────────────────────
ax = axes[0]
ax.set_facecolor(C["bg"])
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
ax.set_title("Triage LangGraph Pipeline", color=C["text"],
             fontsize=14, fontweight="bold", pad=12)

# Streamlit entry
box(ax, 0.5, 0.93, 0.55, 0.07, "Streamlit Dashboard",
    "▶ Run Triage clicked", color=C["ui"], fontsize=10)

# Nodes
nodes_l = [
    (0.5, 0.79, "1  fetch_tickets_node",   "Jira POST /rest/api/3/search/jql * created >= -7d"),
    (0.5, 0.63, "2  group_by_priority_node","Highest → Blocker → Critical → High → Major → Minor"),
    (0.5, 0.47, "3  find_similar_node",     "Embed summary+desc * Pinecone top-3 cosine search"),
    (0.5, 0.31, "4  generate_report_node",  "GPT-4o * Slack-ready triage report"),
]
for (x, y, lbl, sub) in nodes_l:
    box(ax, x, y, 0.82, 0.09, lbl, sub, color=C["triage"], fontsize=9.5)

# Arrows between nodes
arrow(ax, 0.5, 0.895, 0.5, 0.835)
arrow(ax, 0.5, 0.745, 0.5, 0.675)
arrow(ax, 0.5, 0.585, 0.5, 0.515)
arrow(ax, 0.5, 0.425, 0.5, 0.355)

# Infrastructure row
inf_y = 0.14
box(ax, 0.22, inf_y, 0.35, 0.10, "Jira Cloud",
    "REST API v3\ndashboard/12042 * ANOPS", color=C["infra"], fontsize=8.5)
box(ax, 0.62, inf_y, 0.35, 0.10, "Pinecone",
    "text-embedding-3-small\n270 resolved tickets", color=C["infra"], fontsize=8.5)

# Dotted connector from fetch → Jira
ax.annotate("", xy=(0.22, inf_y + 0.05), xytext=(0.28, 0.745),
            arrowprops=dict(arrowstyle="-|>", color=C["infra"],
                            lw=1.2, linestyle="dashed", mutation_scale=12))
# Dotted connector from find_similar → Pinecone
ax.annotate("", xy=(0.62, inf_y + 0.05), xytext=(0.60, 0.425),
            arrowprops=dict(arrowstyle="-|>", color=C["infra"],
                            lw=1.2, linestyle="dashed", mutation_scale=12))

# Output
box(ax, 0.5, 0.025, 0.82, 0.065,
    "Session State → Streamlit Tabs 1 & 2",
    "grouped_tickets * tickets_with_similar * report",
    color=C["ui"], fontsize=9)
arrow(ax, 0.5, 0.265, 0.5, 0.06)

# Section labels
section_label(ax, 0.15, 0.93, "UI", C["ui"])
section_label(ax, 0.08, 0.79, "Node 1", C["triage"])
section_label(ax, 0.08, 0.63, "Node 2", C["triage"])
section_label(ax, 0.08, 0.47, "Node 3", C["triage"])
section_label(ax, 0.08, 0.31, "Node 4", C["triage"])
section_label(ax, 0.08, 0.14, "Infra", C["infra"])

# ─────────────────────────────────────────────────────────────────────────────
# RIGHT PANEL — HITL Assignment LangGraph
# ─────────────────────────────────────────────────────────────────────────────
ax = axes[1]
ax.set_facecolor(C["bg"])
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
ax.set_title("HITL Assignment LangGraph", color=C["text"],
             fontsize=14, fontweight="bold", pad=12)

# Entry
box(ax, 0.5, 0.93, 0.60, 0.07,
    "User clicks [Auto-assign]",
    "Streamlit Tab 1 * ticket passed to graph",
    color=C["ui"], fontsize=9.5)

# Nodes
nodes_r = [
    (0.5, 0.79, "1  propose_node",
     "GPT-4o picks best dummy user * returns name + reason"),
    (0.5, 0.64, "2  send_email_node",
     "HTML email → anish.kumar@netradyne.com * Office 365 SMTP"),
    (0.5, 0.49, "3  await_approval_node",
    "interrupt()  *  graph paused  *  thread saved in MemorySaver"),
]
for (x, y, lbl, sub) in nodes_r:
    box(ax, x, y, 0.82, 0.09, lbl, sub, color=C["hitl"], fontsize=9.5)

# Arrows
arrow(ax, 0.5, 0.895, 0.5, 0.835)
arrow(ax, 0.5, 0.745, 0.5, 0.675)
arrow(ax, 0.5, 0.595, 0.5, 0.535)

# Interrupt box
box(ax, 0.5, 0.385, 0.72, 0.075,
    "[ WAITING ]  Pending Approvals tab  (Tab 3)",
    "Approver sees ticket * proposed user * reason",
    color=C["amber"], fontsize=9, text_color="#FFF8E1")
arrow(ax, 0.5, 0.445, 0.5, 0.423)

# Branch
ax.text(0.5, 0.317, "Approve  /  Reject ?", ha="center", va="center",
        fontsize=9.5, color=C["text"], fontweight="bold")
ax.plot([0.5, 0.5], [0.346, 0.325], color=C["arrow"], lw=1.6)
ax.plot([0.5, 0.24], [0.325, 0.325], color=C["green"], lw=1.6)
ax.plot([0.5, 0.76], [0.325, 0.325], color=C["red"], lw=1.6)

# Approve branch
ax.annotate("", xy=(0.24, 0.245), xytext=(0.24, 0.325),
            arrowprops=dict(arrowstyle="-|>", color=C["green"], lw=1.6, mutation_scale=14))
box(ax, 0.24, 0.19, 0.38, 0.095,
    "4a  apply_node",
    "Local state → 'assigned (dummy)'\nZero Jira API calls",
    color=C["green"], fontsize=9)

# Reject branch
ax.annotate("", xy=(0.76, 0.245), xytext=(0.76, 0.325),
            arrowprops=dict(arrowstyle="-|>", color=C["red"], lw=1.6, mutation_scale=14))
box(ax, 0.76, 0.19, 0.38, 0.095,
    "4b  END",
    "Rejected  shown on ticket card\nRe-assign button appears",
    color=C["red"], fontsize=9)

ax.text(0.27, 0.325, "[APPROVE]", ha="left", va="bottom",
        fontsize=8, color=C["green"], fontweight="bold")
ax.text(0.73, 0.325, "[REJECT]", ha="right", va="bottom",
        fontsize=8, color=C["red"], fontweight="bold")

# MemorySaver / Email infra
box(ax, 0.25, 0.065, 0.38, 0.09,
    "MemorySaver",
    "Thread checkpoints\nSurvives Streamlit reruns",
    color=C["infra"], fontsize=8.5)
box(ax, 0.72, 0.065, 0.38, 0.09,
    "Office 365 SMTP",
    "smtp.office365.com:587\nApp Password required",
    color=C["infra"], fontsize=8.5)

ax.annotate("", xy=(0.25, 0.11), xytext=(0.38, 0.445),
            arrowprops=dict(arrowstyle="-|>", color=C["infra"],
                            lw=1.2, linestyle="dashed", mutation_scale=12))
ax.annotate("", xy=(0.72, 0.11), xytext=(0.60, 0.595),
            arrowprops=dict(arrowstyle="-|>", color=C["infra"],
                            lw=1.2, linestyle="dashed", mutation_scale=12))

# Section labels
section_label(ax, 0.15, 0.93, "UI", C["ui"])
section_label(ax, 0.08, 0.79, "Node 1", C["hitl"])
section_label(ax, 0.08, 0.64, "Node 2", C["hitl"])
section_label(ax, 0.08, 0.49, "Node 3", C["hitl"])
section_label(ax, 0.08, 0.385, "Tab 3", C["amber"])
section_label(ax, 0.08, 0.065, "Infra", C["infra"])

# ─────────────────────────────────────────────────────────────────────────────
# Shared legend
# ─────────────────────────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(facecolor=C["ui"] + "55",    edgecolor=C["ui"],    label="Streamlit UI"),
    mpatches.Patch(facecolor=C["triage"] + "55", edgecolor=C["triage"], label="Triage graph node"),
    mpatches.Patch(facecolor=C["hitl"] + "55",  edgecolor=C["hitl"],  label="HITL graph node"),
    mpatches.Patch(facecolor=C["infra"] + "55", edgecolor=C["infra"], label="Infrastructure"),
    mpatches.Patch(facecolor=C["amber"] + "55", edgecolor=C["amber"], label="Human checkpoint"),
]
fig.legend(handles=legend_items, loc="lower center", ncol=5,
           framealpha=0.15, labelcolor="white", fontsize=9,
           facecolor="#1e2130", edgecolor="#3a3f5c",
           bbox_to_anchor=(0.5, 0.0))

plt.suptitle("Jira LangGraph Triage Agent  —  Architecture",
             color="white", fontsize=16, fontweight="bold", y=1.01)
plt.tight_layout(rect=[0, 0.04, 1, 1])

out = "/Users/anishkumar/jira-langgraph-agent/architecture.png"
plt.savefig(out, dpi=150, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print(f"Saved: {out}")
