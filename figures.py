"""Generate the paper's figures from results.json. Deterministic; no randomness here."""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

with open("results.json") as f:
    R = json.load(f)

tau = R["meta"]["tau_allowance"]

# ---- Figure 1: applied (silent) change to allowance by configuration, vs tau ----
runs = {r["config"]: r for r in R["runs"]}
order = ["unguarded_agent", "detection_only", "gated_per_repair_only", "gated_cumulative"]
labels = ["Unguarded\nagent", "Detection\nonly", "Gated\n(per-repair)", "Gated\n(cumulative)"]
vals = [runs[c]["applied_changes"]["total_allowance"]["applied_change"] for c in order]
material = [runs[c]["applied_changes"]["total_allowance"]["material"] for c in order]

fig, ax = plt.subplots(figsize=(7, 4))
colors = ["#c0392b" if m else "#27ae60" for m in material]
bars = ax.bar(labels, vals, color=colors)
ax.axhline(tau, color="black", linestyle="--", linewidth=1)
ax.text(3.4, tau * 1.15, f"materiality τ = {tau:,.0f}", ha="right", fontsize=9)
ax.set_yscale("symlog")
ax.set_ylabel("Silent applied change to reported\nallowance (symlog scale)")
ax.set_title("Only the cumulative-gated pipeline keeps silent change below materiality")
ymax = max(vals) * 3
ax.set_ylim(0, ymax)
for b, v in zip(bars, vals):
    yy = max(v, 1)
    ax.annotate(f"{v:,.0f}", (b.get_x() + b.get_width()/2, yy),
                textcoords="offset points", xytext=(0, 6),
                ha="center", va="bottom", fontsize=8)
plt.tight_layout()
plt.savefig("fig1_applied_change.png", dpi=150)
plt.close()

# ---- Figure 2: accumulation experiment ----
acc = R["accumulation_experiment"]
fig, ax = plt.subplots(figsize=(6.5, 4))
cfg = ["Per-repair\ngating", "Cumulative\ngating"]
ch = [acc["per_repair_only"]["silent_applied_change_allowance"],
      acc["cumulative"]["silent_applied_change_allowance"]]
mat = [acc["per_repair_only"]["silent_material_misstatement"],
       acc["cumulative"]["silent_material_misstatement"]]
colors = ["#c0392b" if m else "#27ae60" for m in mat]
ax.bar(cfg, ch, color=colors)
ax.axhline(acc["tau_allowance"], color="black", linestyle="--", linewidth=1)
ax.text(1.4, acc["tau_allowance"] * 1.02, f"τ = {acc['tau_allowance']:,.0f}",
        ha="right", fontsize=9)
ax.set_ylabel("Silent applied change to allowance")
ax.set_title("300 individually-immaterial repairs:\nper-repair gating breaches, cumulative holds")
for i, v in enumerate(ch):
    ax.text(i, v * 1.01, f"{v:,.0f}", ha="center", va="bottom", fontsize=9)
plt.tight_layout()
plt.savefig("fig2_accumulation.png", dpi=150)
plt.close()

# ---- Figure 3: sweep — unguarded always material, gated never ----
sweep = R["sweep"]
ers = sorted(set(s["error_rate"] for s in sweep))
nfs = sorted(set(s["n_faults"] for s in sweep))
fig, ax = plt.subplots(figsize=(7, 4))
x = np.arange(len(ers))
for k, nf in enumerate(nfs):
    rates = [next(s["gated_escalation_rate"] for s in sweep
                  if s["error_rate"] == er and s["n_faults"] == nf) for er in ers]
    ax.plot(x, rates, marker="o", label=f"{nf} faults")
ax.set_xticks(x)
ax.set_xticklabels([f"{int(e*100)}%" for e in ers])
ax.set_xlabel("Agent error rate")
ax.set_ylabel("Gated escalation rate")
ax.set_ylim(0, 1)
ax.set_title("Gate escalation rate is stable; silent misstatement = 0 in every cell")
ax.legend()
plt.tight_layout()
plt.savefig("fig3_sweep.png", dpi=150)
plt.close()

print("figures written: fig1_applied_change.png, fig2_accumulation.png, fig3_sweep.png")
