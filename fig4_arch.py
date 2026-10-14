"""Generate fig4: the gate as a write-tool interceptor in an agentic pipeline (paper architecture figure)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(7.4, 3.6))
ax.set_xlim(0, 100); ax.set_ylim(0, 52); ax.axis("off")

def box(x, y, w, h, title, sub, fc, ec):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2",
                                fc=fc, ec=ec, lw=1.0))
    ax.text(x + w/2, y + h*0.62, title, ha="center", va="center", fontsize=9, weight="medium")
    if sub:
        ax.text(x + w/2, y + h*0.26, sub, ha="center", va="center", fontsize=7.2, color="#444")

def arrow(x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=11, lw=1.0, color="#555"))

# top row: detect -> agent -> gate
box(2, 38, 20, 11, "Detector", "flags broken records", "#F1EFE8", "#5F5E5A")
arrow(22, 43.5, 28, 43.5)
box(28, 38, 22, 11, "LLM repair agent", "proposes a fix (may be wrong)", "#FAEEDA", "#854F0B")
arrow(50, 43.5, 56, 43.5)
box(56, 38, 22, 11, "Compute Δ", "effect on the figure", "#E6F1FB", "#185FA5")

# gate
arrow(67, 38, 67, 32)
box(30, 20, 44, 11, "Materiality gate (write-tool interceptor)",
    "|Δ| below line?  control totals tied out?  finite?", "#E6F1FB", "#185FA5")

# branches
arrow(45, 20, 33, 14)
ax.text(28, 17.5, "admissible", fontsize=7.2, color="#3B6D11")
arrow(60, 20, 68, 14)
ax.text(74, 17.5, "not admissible", fontsize=7.2, color="#A32D2D")

box(10, 2, 30, 11, "Commit write", "applied; running total updated", "#EAF3DE", "#3B6D11")
box(60, 2, 32, 11, "Human review queue", "ranked by severity, held", "#FCEBEB", "#A32D2D")

plt.tight_layout()
plt.savefig("fig4_architecture.png", dpi=150, bbox_inches="tight")
plt.close()
print("fig4_architecture.png written")
