"""
Experiments for matrepair. Every number the paper reports is produced here.
Run: python experiments.py  ->  writes results.json and figures.
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from matrepair import (make_cecl_instance, inject_faults, agent_propose,
                       MaterialityGate)


def oracle_truth_figures(inst):
    """Reported figures if the dataset were the ground truth (perfect repair)."""
    return {a.name: a.value(inst.truth) for a in inst.aggregates}


def figures(inst, df):
    return {a.name: a.value(df) for a in inst.aggregates}


def silent_misstatement(inst, applied_df):
    """
    The property the gate actually guarantees (theory.md Section 5):
    the SILENTLY auto-applied changes must not cause a material misstatement or
    break a control total. We measure the change the applied dataset introduces
    RELATIVE TO THE CORRUPTED BASELINE inst.df -- i.e. what the automation changed
    without human sign-off -- and ask whether THAT change is material.

    Escalated (unapplied) repairs leave records corrupted; that residual error is
    pending human review, NOT a silent automated misstatement, so it is excluded.
    """
    out = {}
    for a in inst.aggregates:
        applied_change = abs(a.value(applied_df) - a.value(inst.df))  # what automation moved
        if a.is_control_total:
            out[a.name] = {"applied_change": applied_change,
                           "material": applied_change > 1e-6, "kind": "control_total"}
        else:
            out[a.name] = {"applied_change": applied_change,
                           "material": applied_change >= a.tau, "kind": "materiality",
                           "tau": a.tau}
    return out


def residual_error_vs_truth(inst, applied_df):
    """Diagnostic only: how far the post-automation report still is from perfect-repair
    truth (this is expected to be nonzero -- it is the work left for human reviewers)."""
    truth = oracle_truth_figures(inst)
    return {a.name: round(abs(a.value(applied_df) - truth[a.name]), 2) for a in inst.aggregates}


def config_unguarded(inst, proposals):
    """Apply EVERY proposed repair with no gate (the unguarded LLM-agent baseline)."""
    df = inst.df.copy(deep=True)
    for i, row in proposals.items():
        df.loc[i] = row
    escalated = 0
    return df, escalated


def config_detection_only(inst, proposals):
    """
    Detection-only baseline (represents existing best-effort/detect benchmarks):
    detects that a record was flagged, but applies no automated repair and escalates
    NOTHING selectively -- it simply leaves corrupted records unrepaired.
    (Models a system that detects but has no safe-repair concept.)
    """
    df = inst.df.copy(deep=True)   # corrupted values left in place
    escalated = 0
    return df, escalated


def config_gated(inst, proposals, cumulative=True):
    gate = MaterialityGate(inst, cumulative=cumulative)
    applied, decisions = gate.run(proposals)
    escalated = sum(1 for d in decisions if not d.admissible)
    return applied, escalated, decisions


def score_run(name, inst, df, escalated, proposals, decisions=None):
    mis = silent_misstatement(inst, df)
    any_material = any(v["material"] for v in mis.values())
    n_prop = len(proposals)
    auto_applied = n_prop - escalated
    row = {
        "config": name,
        "n_proposals": n_prop,
        "auto_applied": auto_applied,
        "escalated": escalated,
        "escalation_rate": round(escalated / n_prop, 4) if n_prop else 0.0,
        "silent_material_misstatement": bool(any_material),   # THE safety axis
        "applied_changes": {k: {"applied_change": round(v["applied_change"], 2),
                                "material": bool(v["material"])}
                            for k, v in mis.items()},
        "residual_error_vs_truth": residual_error_vs_truth(inst, df),  # pending human work
    }
    return row


def priority_quality(inst, decisions):
    """
    Materiality-tiered prioritization axis: among escalated repairs, does severity
    rank the truly-largest-impact repairs first? Report Spearman corr between the
    gate's severity score and the true |Delta_allowance|.
    """
    from scipy.stats import spearmanr
    esc = [d for d in decisions if not d.admissible and np.isfinite(d.severity)]
    if len(esc) < 3:
        return None
    sev = [d.severity for d in esc]
    true_impact = [abs(d.deltas["total_allowance"]) for d in esc]
    rho, _ = spearmanr(sev, true_impact)
    return round(float(rho), 4)


def main():
    results = {"runs": [], "meta": {}}

    inst0 = make_cecl_instance(n_loans=20000, seed=0)
    truth = oracle_truth_figures(inst0)
    results["meta"]["truth_figures"] = {k: round(v, 2) for k, v in truth.items()}
    results["meta"]["tau_allowance"] = round(inst0.aggregates[0].tau, 2)
    results["meta"]["control_total_exposure"] = round(inst0.control_totals["total_exposure"], 2)

    # Fresh instance per config (fault injection mutates in place)
    def fresh():
        inst = make_cecl_instance(n_loans=20000, seed=0)
        inject_faults(inst, n_faults=400, seed=1)
        proposals = agent_propose(inst, seed=2, error_rate=0.25)
        return inst, proposals

    # --- Config 1: unguarded agent ---
    inst, proposals = fresh()
    df, esc = config_unguarded(inst, proposals)
    results["runs"].append(score_run("unguarded_agent", inst, df, esc, proposals))

    # --- Config 2: detection-only ---
    inst, proposals = fresh()
    df, esc = config_detection_only(inst, proposals)
    results["runs"].append(score_run("detection_only", inst, df, esc, proposals))

    # --- Config 3: gated (cumulative) ---
    inst, proposals = fresh()
    df, esc, decisions = config_gated(inst, proposals, cumulative=True)
    row = score_run("gated_cumulative", inst, df, esc, proposals, decisions)
    row["priority_spearman"] = priority_quality(inst, decisions)
    results["runs"].append(row)

    # --- Config 4: gated but per-repair only (shows the accumulation failure mode) ---
    inst, proposals = fresh()
    df, esc, decisions = config_gated(inst, proposals, cumulative=False)
    results["runs"].append(score_run("gated_per_repair_only", inst, df, esc, proposals, decisions))

    # --- Robustness sweep: vary agent error rate and fault count ---
    sweep = []
    for er in [0.0, 0.1, 0.25, 0.5]:
        for nf in [200, 400, 800]:
            inst = make_cecl_instance(n_loans=20000, seed=0)
            inject_faults(inst, n_faults=nf, seed=1)
            proposals = agent_propose(inst, seed=2, error_rate=er)
            # unguarded
            dfu = inst.df.copy(deep=True)
            for i, r in proposals.items():
                dfu.loc[i] = r
            mis_u = any(v["material"] for v in silent_misstatement(inst, dfu).values())
            # gated
            g = MaterialityGate(inst, cumulative=True)
            dfg, decs = g.run(proposals)
            mis_g = any(v["material"] for v in silent_misstatement(inst, dfg).values())
            escg = sum(1 for d in decs if not d.admissible)
            sweep.append({"error_rate": er, "n_faults": nf,
                          "unguarded_material": bool(mis_u),
                          "gated_material": bool(mis_g),
                          "gated_escalation_rate": round(escg / nf, 4)})
    results["sweep"] = sweep

    # --- Accumulation experiment: many SMALL repairs, each individually immaterial,
    #     that cumulatively breach materiality. Shows per-repair gating is unsafe and
    #     cumulative gating (Section 7.2) is the fix. ---
    def small_repairs_instance():
        inst = make_cecl_instance(n_loans=20000, seed=0)
        tau = inst.aggregates[0].tau
        # Inject 300 faults each of which, when repaired, moves allowance by ~ (0.6..0.9)*(tau/K)
        # so that individually |Delta| < tau but the sum of many exceeds tau.
        rng = np.random.default_rng(7)
        idx = rng.choice(inst.df.index.to_numpy(), size=300, replace=False)
        # Corrupt pd slightly low; the "repair" nudges pd up by a small per-loan amount.
        per_repair_target = 0.9 * tau / 60.0   # ~60 such repairs would breach tau
        proposals = {}
        inst.corrupted_idx = sorted(int(x) for x in idx)
        inst.fault_types = {int(x): "small_pd_drift" for x in idx}
        for i in idx:
            i = int(i)
            rec = inst.df.loc[i].copy()
            expo, lgd = rec["exposure"], rec["lgd"]
            # choose delta_pd so exposure*delta_pd*lgd ~ per_repair_target
            denom = max(expo * lgd, 1e-6)
            delta_pd = per_repair_target / denom
            # corrupt: set pd lower by delta_pd; repair proposes original (raise back)
            inst.df.loc[i, "pd"] = max(rec["pd"] - delta_pd, 1e-4)
            rec2 = inst.df.loc[i].copy()
            rec2["pd"] = rec["pd"]   # the repair restores it -> per-repair effect ~ per_repair_target
            proposals[i] = rec2
        return inst, proposals, tau

    inst_a, prop_a, tau_a = small_repairs_instance()
    # per-repair-only gate
    g_pr = MaterialityGate(inst_a, cumulative=False)
    df_pr, dec_pr = g_pr.run(prop_a)
    esc_pr = sum(1 for d in dec_pr if not d.admissible)
    mis_pr = silent_misstatement(inst_a, df_pr)
    # cumulative gate on a fresh copy
    inst_b, prop_b, _ = small_repairs_instance()
    g_cu = MaterialityGate(inst_b, cumulative=True)
    df_cu, dec_cu = g_cu.run(prop_b)
    esc_cu = sum(1 for d in dec_cu if not d.admissible)
    mis_cu = silent_misstatement(inst_b, df_cu)

    results["accumulation_experiment"] = {
        "tau_allowance": round(tau_a, 2),
        "n_small_repairs": len(prop_a),
        "per_repair_only": {
            "auto_applied": len(prop_a) - esc_pr,
            "escalated": esc_pr,
            "silent_applied_change_allowance": round(mis_pr["total_allowance"]["applied_change"], 2),
            "silent_material_misstatement": bool(mis_pr["total_allowance"]["material"]),
        },
        "cumulative": {
            "auto_applied": len(prop_b) - esc_cu,
            "escalated": esc_cu,
            "silent_applied_change_allowance": round(mis_cu["total_allowance"]["applied_change"], 2),
            "silent_material_misstatement": bool(mis_cu["total_allowance"]["material"]),
        },
    }

    with open("results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
