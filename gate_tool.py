"""
gate_tool.py — realizing the MaterialityGate as an interceptor on an agent's write tool.

This is the integration point described in the paper (Section 4.4 / Discussion): an LLM
or agentic proposer is given a `write_fix` tool; we interpose the gate so a proposed
repair is committed only if admissible, else enqueued for human review. The gate is
deterministic code, not a model -- it composes with agent-safety enforcement frameworks
(e.g. runtime tool-call monitors) by supplying the materiality predicate they cannot
themselves express.

The proposer is intentionally abstract: any callable that returns a repaired record for a
flagged index plugs into the same interface. The scripted proposer used in the benchmark,
a live LLM, or a ReAct agent are all instances of `RepairProposer`.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol
import pandas as pd
from matrepair import ReportingInstance, MaterialityGate, GateDecision


class RepairProposer(Protocol):
    """Any proposer -- heuristic, LLM, or agent -- implements this one method."""
    def propose(self, inst: ReportingInstance, idx: int) -> pd.Series: ...


@dataclass
class ReviewItem:
    idx: int
    proposed: pd.Series
    decision: GateDecision


@dataclass
class GatedWriteTool:
    """
    Interceptor around an agent's write capability. The agent never writes directly;
    it calls `write_fix`, which consults the gate. Admissible repairs are committed and
    the running materiality total is updated; the rest are routed to `review_queue`,
    ranked by severity (materiality-tiered prioritization).
    """
    inst: ReportingInstance
    cumulative: bool = True
    gate: MaterialityGate = field(init=False)
    applied: pd.DataFrame = field(init=False)
    review_queue: list[ReviewItem] = field(default_factory=list)

    def __post_init__(self):
        self.gate = MaterialityGate(self.inst, cumulative=self.cumulative)
        self.applied = self.inst.df.copy(deep=True)

    def write_fix(self, idx: int, repaired_row: pd.Series) -> GateDecision:
        """The gated tool call the agent invokes instead of a raw write."""
        dec = self.gate.decide(idx, repaired_row)
        if dec.admissible:
            self.applied.loc[idx] = repaired_row
            if self.cumulative:
                for a in self.inst.aggregates:
                    self.gate.running[a.name] += dec.deltas[a.name]
        else:
            self.review_queue.append(ReviewItem(idx, repaired_row, dec))
        return dec

    def prioritized_review_queue(self) -> list[ReviewItem]:
        """Most consequential escalations first (severity = max_j |Delta_j|/tau_j)."""
        return sorted(self.review_queue, key=lambda r: r.decision.severity, reverse=True)


def run_agentic_pipeline(inst: ReportingInstance, proposer: RepairProposer,
                         cumulative: bool = True) -> GatedWriteTool:
    """
    Drive the loop: for each flagged (corrupted) record, the proposer proposes a fix and
    the agent 'writes' it through the gated tool. Returns the tool with committed writes
    and the human-review queue populated.
    """
    tool = GatedWriteTool(inst, cumulative=cumulative)
    for idx in inst.corrupted_idx:
        repaired = proposer.propose(inst, idx)
        tool.write_fix(idx, repaired)
    return tool


if __name__ == "__main__":
    # Demonstration: wrap the benchmark's scripted proposer in the RepairProposer interface
    # and drive it through the gated tool. Shows the identical safety outcome via the
    # tool-interceptor path that an agent framework would use.
    from matrepair import make_cecl_instance, inject_faults, agent_propose

    class ScriptedProposer:
        def __init__(self, inst, seed=2, error_rate=0.25):
            self._cache = agent_propose(inst, seed=seed, error_rate=error_rate)
        def propose(self, inst, idx):
            return self._cache[idx]

    inst = make_cecl_instance(n_loans=20000, seed=0)
    inject_faults(inst, n_faults=400, seed=1)
    tool = run_agentic_pipeline(inst, ScriptedProposer(inst), cumulative=True)

    applied_change = abs(inst.aggregates[0].value(tool.applied)
                         - inst.aggregates[0].value(inst.df))
    tau = inst.aggregates[0].tau
    print(f"committed writes: {len(inst.corrupted_idx) - len(tool.review_queue)}")
    print(f"escalated to review: {len(tool.review_queue)}")
    print(f"silent applied change to allowance: {applied_change:,.2f} (tau {tau:,.2f})")
    print(f"silent material misstatement: {applied_change >= tau}")
    top = tool.prioritized_review_queue()[:3]
    print("top-3 escalations by severity:",
          [(t.idx, round(t.decision.severity, 2)) for t in top])
