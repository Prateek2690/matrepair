# matrepair — Materiality-Bounded Repair Safety

[![DOI](https://zenodo.org/badge/1418606691.svg)](https://doi.org/10.5281/zenodo.23362560)

A reusable benchmark and reference implementation for **materiality-bounded, reconciliation-preserving
repair safety** in the automated correction of regulated financial figures.

Companion code for:

> Bhatnagar, P. (2026). *A Safety Gate for AI-Driven Data Repair in Regulated Financial Reporting:
> Escalating Only the Fixes That Could Materially Misstate a Reported Figure.*
> SSRN working paper, posted 15 September 2026.
> [SSRN abstract 7432699](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7432699) · DOI `10.2139/ssrn.7432699`
>
> *Preprint — not peer reviewed.*

## What this is

Automated and agentic data-repair systems fix broken inputs to regulated reports, such as a CECL
allowance. Most fixes are harmless. A few can move a **reported figure** past its **materiality
threshold** and be applied with no human sign-off.

This repository implements a deterministic **verification gate** that auto-applies only *admissible*
repairs — those that are materiality-bounded and reconciliation-preserving — and escalates the rest,
with a **completeness guarantee**: no auto-applied repair can cause a silent material misstatement or
break a control total.

The gate is proposer-agnostic. It bounds the *effect* of a repair on the reported figure, not the
competence of whatever proposed it, so it composes with existing agent-guardrail mechanisms rather
than replacing them.

## Contents

| File | Purpose |
|---|---|
| `matrepair.py` | Reporting-instance model, synthetic CECL generator, fault injection, repair proposer, `MaterialityGate` |
| `experiments.py` | Runs all configurations and writes `results.json`. Every number in the paper comes from here |
| `figures.py` | Regenerates figures 1–3 from `results.json` |
| `fig4_arch.py` | Architecture figure |
| `gate_tool.py` | The gate as an interceptor on an agent's `write_fix` tool (agentic-pipeline integration, §4.4). Reproduces the batch safety result via the agent-tool path |
| `theory.md` | Formal model, admissibility property, completeness proof, boundaries |
| `results.json` | Produced results, reproducible from a fixed seed |

## Reproduce

```bash
pip install -r requirements.txt
python experiments.py    # writes results.json
python figures.py        # writes fig1/fig2/fig3 png
python fig4_arch.py      # writes fig4 png
```

Runs are byte-identical across invocations (fixed seeds). To verify:

```bash
python experiments.py > a.json
python experiments.py > b.json
diff a.json b.json       # expected: empty
```

## Key results

All drawn from `results.json`. Materiality threshold τ ≈ $435K on a reported allowance of ≈ $87.08M.

| Configuration | Silent change to reported allowance | Material? | Control total |
|---|---|---|---|
| Unguarded agent | ≈ $466M | Yes | Broken |
| Detection only (repairs nothing) | $0 | No | Intact |
| Gated, per-repair accounting | ≈ $866K | **Yes** | Intact |
| Gated, cumulative accounting | $435,225 | No | Exact |

Per-repair gating still breaches materiality: individually admissible repairs accumulate. Only
cumulative accounting holds the silent change below τ while still auto-applying 104 immaterial
repairs and escalating 296.

Across a sweep of agent error rates {0, 0.1, 0.25, 0.5} × fault counts {200, 400, 800} — twelve
cells — the unguarded pipeline produces a material silent misstatement in **every** cell and the
cumulative-gated pipeline in **none**.

## Scope and limitations

The completeness result is scoped to **additively decomposable** figures: sums, subtotals, and
weighted sums, which are the dominant forms of regulatory aggregation. For Lipschitz-but-non-
decomposable aggregates such as ratios and percentiles, the paper gives a bounded extension that
preserves completeness at the cost of additional escalations; its empirical evaluation is left to
follow-up work.

The gate guarantees that a repair is *safe to auto-apply*, not that it is *correct*. A wrong but
immaterial repair is applied by design, since it cannot materially misstate the report. Value
correctness remains the proposer's responsibility.

## Citing the code

Software archive on Zenodo: DOI [10.5281/zenodo.23362560](https://doi.org/10.5281/zenodo.23362560). Please also cite the paper above.

## Author

Prateek Bhatnagar — Independent Researcher — ORCID [0009-0000-0359-3268](https://orcid.org/0009-0000-0359-3268)

## License

MIT. See `LICENSE`.
