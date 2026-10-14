"""
matrepair — a benchmark for materiality-bounded repair safety in regulated reporting.

Everything here is synthetic with ground truth known by construction. No proprietary
data, no external calls. Reproducible from a fixed seed.

Core objects:
  - ReportingInstance: dataset D, aggregates A (additively decomposable), thresholds tau,
    optional control totals T.
  - Fault injection: corrupt records in known ways, recording the true (pre-corruption) value.
  - Repair strategies: propose a fix for each corrupted record.
  - MaterialityGate: the deterministic gate G that auto-applies admissible repairs and
    escalates the rest, with a completeness guarantee (see theory.md, Section 5).
  - Scoring: repair-safety, reconciliation-to-control-total, materiality-tiered prioritization.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Callable


# --------------------------------------------------------------------------------------
# Reporting instance
# --------------------------------------------------------------------------------------

@dataclass
class Aggregate:
    """An additively-decomposable reported figure: a_j(D) = sum_i contribution(r_i)."""
    name: str
    contribution: Callable[[pd.Series], float]   # per-record contribution c_j(r_i)
    tau: float                                    # materiality threshold
    is_control_total: bool = False                # if True, must reconcile exactly (Delta must be 0)

    def value(self, df: pd.DataFrame) -> float:
        return float(df.apply(self.contribution, axis=1).sum())

    def contrib_vector(self, df: pd.DataFrame) -> np.ndarray:
        return df.apply(self.contribution, axis=1).to_numpy(dtype=float)


@dataclass
class ReportingInstance:
    df: pd.DataFrame                 # current (possibly corrupted) dataset D
    aggregates: list[Aggregate]
    truth: pd.DataFrame             # ground-truth dataset (pre-corruption), same index
    corrupted_idx: list[int] = field(default_factory=list)
    control_totals: dict[str, float] = field(default_factory=dict)  # name -> T_j (from truth)

    def true_effect(self, agg: Aggregate, repaired_df: pd.DataFrame, touched: list[int]) -> float:
        """Delta_j(rho) computed exactly over only touched records (Section 4)."""
        before = agg.contrib_vector(self.df.loc[touched])
        after = agg.contrib_vector(repaired_df.loc[touched])
        return float((after - before).sum())


# --------------------------------------------------------------------------------------
# Synthetic generator: a stylized CECL-like allowance dataset
# --------------------------------------------------------------------------------------

def make_cecl_instance(n_loans: int = 20000, seed: int = 0) -> ReportingInstance:
    """
    Stylized loan book. Each loan has:
      exposure (EAD), pd (prob of default), lgd (loss given default).
    Reported aggregates (all additively decomposable):
      - total_allowance = sum(exposure * pd * lgd)            [tolerance-materiality]
      - total_exposure  = sum(exposure)                        [control total, must reconcile]
    """
    rng = np.random.default_rng(seed)
    exposure = np.round(rng.lognormal(mean=11.5, sigma=1.1, size=n_loans), 2)   # ~ tens of thousands
    pd_ = np.clip(rng.beta(1.5, 30, size=n_loans), 1e-4, 0.9)
    lgd = np.clip(rng.beta(4, 4, size=n_loans), 0.05, 0.95)

    df = pd.DataFrame({
        "loan_id": np.arange(n_loans),
        "exposure": exposure,
        "pd": np.round(pd_, 6),
        "lgd": np.round(lgd, 4),
    })

    aggregates = [
        Aggregate("total_allowance",
                  lambda r: r["exposure"] * r["pd"] * r["lgd"],
                  tau=0.0, is_control_total=False),   # tau set below, relative to scale
        Aggregate("total_exposure",
                  lambda r: r["exposure"],
                  tau=0.0, is_control_total=True),
    ]

    truth = df.copy(deep=True)
    inst = ReportingInstance(df=df, aggregates=aggregates, truth=truth)

    # Materiality thresholds: allowance materiality at 0.5% of reported allowance
    # (a common quantitative materiality benchmark band is 0.5-1% of the relevant base).
    alloc = aggregates[0].value(df)
    aggregates[0].tau = 0.005 * alloc
    # Control total: exposure must reconcile exactly (tau irrelevant; hard constraint).
    aggregates[1].tau = 0.0
    inst.control_totals["total_exposure"] = aggregates[1].value(truth)
    return inst


# --------------------------------------------------------------------------------------
# Fault injection: corrupt records in known ways, ground truth retained in inst.truth
# --------------------------------------------------------------------------------------

def inject_faults(inst: ReportingInstance, n_faults: int = 400, seed: int = 1) -> ReportingInstance:
    """
    Corrupt n_faults records. Fault types (all recoverable in principle):
      - missing_pd:     pd set to NaN
      - scale_error:    exposure off by 1000x (unit error: dollars vs thousands)
      - sign_flip:      lgd negated (illegal, must be in [0,1])
      - digit_typo:     exposure gets an extra digit (10x)
    The magnitude of the eventual repair effect varies by fault + by the loan's size,
    so some repairs are immaterial and some are material -- known by construction.
    """
    rng = np.random.default_rng(seed)
    idx = rng.choice(inst.df.index.to_numpy(), size=n_faults, replace=False)
    ftypes = rng.choice(["missing_pd", "scale_error", "sign_flip", "digit_typo"], size=n_faults)

    df = inst.df
    for i, ft in zip(idx, ftypes):
        if ft == "missing_pd":
            df.loc[i, "pd"] = np.nan
        elif ft == "scale_error":
            df.loc[i, "exposure"] = df.loc[i, "exposure"] * 1000.0
        elif ft == "sign_flip":
            df.loc[i, "lgd"] = -df.loc[i, "lgd"]
        elif ft == "digit_typo":
            df.loc[i, "exposure"] = df.loc[i, "exposure"] * 10.0

    inst.corrupted_idx = sorted(int(x) for x in idx)
    inst.fault_types = dict(zip((int(x) for x in idx), ftypes))
    return inst


# --------------------------------------------------------------------------------------
# Repair strategies: propose a repaired record for each corrupted index.
# A strategy returns a dict: idx -> repaired pandas Series (full record).
# The "agent" is a stand-in for an LLM repair proposer: it proposes plausible fixes,
# sometimes right, sometimes wrong -- exactly the setting the gate must be safe under.
# --------------------------------------------------------------------------------------

def agent_propose(inst: ReportingInstance, seed: int = 2, error_rate: float = 0.25) -> dict[int, pd.Series]:
    """
    Stand-in agent proposer. For each corrupted record it proposes a fix using simple
    heuristics (median/clip/abs), and with probability `error_rate` it proposes a
    PLAUSIBLE-BUT-WRONG value (e.g. imputes pd from a wrong segment) -- modeling an
    LLM that is confidently wrong. Deterministic given seed.
    """
    rng = np.random.default_rng(seed)
    df = inst.df
    good_pd_median = float(np.nanmedian(df["pd"].to_numpy()))
    proposals: dict[int, pd.Series] = {}
    for i in inst.corrupted_idx:
        rec = df.loc[i].copy()
        ft = inst.fault_types[i]
        wrong = rng.random() < error_rate
        if ft == "missing_pd":
            # right: impute segment median pd; wrong: impute an inflated pd
            rec["pd"] = good_pd_median * (rng.uniform(3, 8) if wrong else 1.0)
        elif ft == "scale_error":
            # right: divide by 1000; wrong: divide by 100 (leaves a 10x error)
            rec["exposure"] = rec["exposure"] / (100.0 if wrong else 1000.0)
        elif ft == "sign_flip":
            # right: abs(); wrong: abs() then inflate
            rec["lgd"] = abs(rec["lgd"]) * (rng.uniform(1.5, 2.5) if wrong else 1.0)
            rec["lgd"] = min(rec["lgd"], 0.99)
        elif ft == "digit_typo":
            # right: divide by 10; wrong: leave as-is (no fix)
            rec["exposure"] = rec["exposure"] / (1.0 if wrong else 10.0)
        proposals[i] = rec
    return proposals


# --------------------------------------------------------------------------------------
# The materiality gate G (Section 4). Applies admissible repairs, escalates the rest.
# --------------------------------------------------------------------------------------

@dataclass
class GateDecision:
    idx: int
    deltas: dict[str, float]
    admissible: bool
    reason: str
    severity: float   # max_j |Delta_j|/tau_j  (materiality-tiered priority; inf if control-total breach)


class MaterialityGate:
    def __init__(self, inst: ReportingInstance, cumulative: bool = True):
        self.inst = inst
        self.cumulative = cumulative
        self.running = {a.name: 0.0 for a in inst.aggregates}

    def _delta(self, agg, repaired_row: pd.Series, i: int) -> float:
        before = agg.contribution(self.inst.df.loc[i])
        after = agg.contribution(repaired_row)
        return float(after - before)

    def decide(self, i: int, repaired_row: pd.Series) -> GateDecision:
        deltas, admissible, reason, severity = {}, True, "admissible", 0.0
        for a in self.inst.aggregates:
            d = self._delta(a, repaired_row, i)
            # Well-definedness precondition (theory.md Section 4.1): a repair whose
            # effect is not a finite real number cannot be certified safe -- escalate.
            if not np.isfinite(d):
                deltas[a.name] = d
                admissible = False
                reason = f"non-finite effect ({a.name})"
                severity = float("inf")
                continue
            # cumulative accounting (Section 7.2): test running + this delta
            effective = (self.running[a.name] + d) if self.cumulative else d
            deltas[a.name] = d
            if a.is_control_total:
                if abs(effective) > 1e-9:   # must reconcile exactly
                    admissible = False
                    reason = f"control-total breach ({a.name})"
                    severity = float("inf")
            else:
                sev = abs(effective) / a.tau if a.tau > 0 else 0.0
                severity = max(severity, sev)
                if abs(effective) >= a.tau:
                    admissible = False
                    if reason == "admissible":
                        reason = f"material ({a.name}: |{effective:.1f}| >= tau {a.tau:.1f})"
        return GateDecision(i, deltas, admissible, reason, severity)

    def run(self, proposals: dict[int, pd.Series]):
        """Process proposals in order; auto-apply admissible, escalate the rest.
        Returns (applied_df, decisions)."""
        applied = self.inst.df.copy(deep=True)
        decisions = []
        for i, row in proposals.items():
            dec = self.decide(i, row)
            decisions.append(dec)
            if dec.admissible:
                applied.loc[i] = row
                if self.cumulative:
                    for a in self.inst.aggregates:
                        self.running[a.name] += dec.deltas[a.name]
        return applied, decisions
