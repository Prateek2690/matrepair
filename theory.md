# Theoretical Core — Materiality-Bounded Repair Safety

## 1. The reported-figure model

A **reporting instance** is a tuple $(D, \mathcal{A}, \tau)$ where:

- $D = \{r_1, \dots, r_n\}$ is a dataset of records. Each record $r_i$ has a set of fields; some fields are numeric inputs to reporting.
- $\mathcal{A} = \{a_1, \dots, a_m\}$ is a set of **reported aggregates**. Each $a_j$ is a function $a_j : \mathcal{D} \to \mathbb{R}$ mapping a dataset to a reported figure (e.g., total CECL allowance, total RWA). We require each $a_j$ to be **additively decomposable**: there exist per-record contributions $c_{j}(r_i)$ with $a_j(D) = \sum_{i} c_{j}(r_i)$. (Sums, subtotals, and weighted sums of record-level quantities satisfy this; it is the dominant form in regulatory aggregation.)
- $\tau = (\tau_1, \dots, \tau_m)$, $\tau_j > 0$, is the **materiality threshold** for aggregate $a_j$ — the magnitude of misstatement in $a_j$ that the reporting regime treats as material.

A **control total** is a reported figure that must reconcile to an independently-computed reference $T_j$: reconciliation holds iff $a_j(D) = T_j$ (or within a stated tolerance $\epsilon_j$; we use exact for clarity and note the tolerance generalization).

## 2. Repairs

A **repair** $\rho$ is a modification of $D$ to $\rho(D)$ that changes one or more records (an imputation, correction, or deletion of a broken value). Define the **effect** of $\rho$ on aggregate $a_j$:
$$
\Delta_j(\rho) \;=\; a_j(\rho(D)) - a_j(D) \;=\; \sum_i \big( c_j(\rho(r_i)) - c_j(r_i) \big).
$$
Because $a_j$ is additively decomposable, $\Delta_j(\rho)$ is the **sum of the per-record contribution changes** the repair induces — this is what makes the effect exactly computable from the repair alone, without recomputing over untouched records.

## 3. The admissibility property (what "safe to auto-apply" means)

A repair $\rho$ is **materiality-admissible** for instance $(D,\mathcal{A},\tau)$ iff
$$
\forall j \in \{1,\dots,m\}: \quad |\Delta_j(\rho)| < \tau_j .
$$
That is: the repair cannot move **any** reported figure by a material amount. A repair that also must preserve a control total $T_j$ is **reconciliation-preserving** iff it does not break an already-satisfied reconciliation:
$$
a_j(D) = T_j \;\Rightarrow\; a_j(\rho(D)) = T_j \quad\text{i.e.}\quad \Delta_j(\rho) = 0 \text{ for control-total aggregates.}
$$

**Admissible = materiality-admissible AND reconciliation-preserving.** Only admissible repairs may be auto-applied; all others are **escalated** to human authorization.

Note the two-tier structure: materiality-admissibility is a *soft* bound ($<\tau_j$) for figures with a tolerance; reconciliation-preservation is a *hard* bound ($=0$) for figures that must tie to a control total exactly. The gate enforces both.

## 4. The verification gate

The **gate** $G$ is the deterministic procedure: given a proposed repair $\rho$, compute $\Delta_j(\rho)$ for every $j$ (a sum over only the records $\rho$ touches), and

- **auto-apply** $\rho$ iff $\rho$ is admissible;
- **escalate** $\rho$ otherwise.

$G$ never inspects untouched records: it evaluates $\sum_{i \in \mathrm{touched}(\rho)} (c_j(\rho(r_i)) - c_j(r_i))$, cost linear in the size of the repair, independent of $n$.

## 4.1 Well-definedness precondition (discovered empirically; required for soundness)

A proposed repair may leave a field non-numeric (e.g. an imputation that fails, leaving `NaN`).
Then $c_j(\rho(r_i))$ and hence $\Delta_j(\rho)$ is not a finite real, and any threshold
comparison $|\Delta_j| \ge \tau_j$ silently evaluates to *false*, causing the gate to
**auto-apply an uncertified repair**. The gate must therefore treat a non-finite effect as
**inadmissible by definition**: $\Delta_j(\rho) \notin \mathbb{R}$ (finite) $\Rightarrow$ escalate.
This is a precondition on $G$, not an optional check; omitting it breaks completeness in the
presence of failed imputations — a failure mode we observed and now guard against explicitly.

## 5. Completeness (the central proposition)

> **Proposition (Materiality Completeness).**
> Let $G$ be the gate of §4. For any proposed repair $\rho$: if $\rho$ is capable of moving some reported figure past its materiality threshold — i.e. $\exists j: |\Delta_j(\rho)| \geq \tau_j$ — or of breaking a control-total reconciliation — i.e. $\exists j$ a control total with $\Delta_j(\rho) \neq 0$ — then $G$ escalates $\rho$. Equivalently: **no repair that $G$ auto-applies can cause a material misstatement or break a reconciliation.**

**Proof.**
$G$ auto-applies $\rho$ only if $\rho$ is admissible (§4). By definition (§3), admissible means $|\Delta_j(\rho)| < \tau_j$ for all $j$ *and* $\Delta_j(\rho)=0$ for every control-total aggregate. Contrapositive: if $\exists j$ with $|\Delta_j(\rho)| \geq \tau_j$, or $\exists$ control-total $j$ with $\Delta_j(\rho) \neq 0$, then $\rho$ is not admissible, so $G$ does not auto-apply it; by the totality of $G$ (it either auto-applies or escalates), $G$ escalates it.

It remains to show $\Delta_j(\rho)$ as computed by $G$ equals the true effect on the reported figure. By additive decomposability (§1), $a_j(\rho(D)) - a_j(D) = \sum_i (c_j(\rho(r_i)) - c_j(r_i))$; for records $\rho$ does not touch, $\rho(r_i)=r_i$ so the summand is $0$. Hence the true effect equals $\sum_{i \in \mathrm{touched}(\rho)}(c_j(\rho(r_i)) - c_j(r_i))$, which is exactly what $G$ computes. Therefore the admissibility test $G$ performs uses the exact effect, and the escalation decision is correct with respect to the true reported figure. $\qquad\blacksquare$

## 6. What the proposition does and does not claim (threats to validity, stated up front)

- **It does NOT claim the repair is correct.** $G$ guarantees a repair is *safe to apply without human sign-off*, not that the imputed value is the true value. A wrong-but-immaterial repair is still auto-applied; that is by design — its wrongness cannot materially misstate the report. Correctness of the value is the detector/proposer's job, out of scope.
- **It depends on additive decomposability.** For aggregates that are *not* additively decomposable (e.g. a ratio, a percentile, a max), $\Delta_j(\rho)$ is not a simple sum of touched-record changes. §7 gives the extension: monotone/Lipschitz aggregates admit a computable bound on $\Delta_j$; the gate then escalates whenever the *bound* exceeds $\tau_j$, preserving completeness at the cost of some extra escalations (soundness relaxes, completeness holds). This is the honest boundary of the result.
- **It assumes correct thresholds $\tau_j$ and control totals $T_j$.** These are regulatory/policy inputs, not derived. A wrong $\tau_j$ mis-sizes materiality; that is a policy error, not a gate error. The gate is complete *relative to* the supplied $\tau$.
- **Interaction / batching.** If repairs are applied in a batch, individual immaterial repairs can sum to a material change. §7.2 handles this: the gate tests the *cumulative* $\sum_k \Delta_j(\rho_k)$ against $\tau_j$ over the batch, escalating the marginal repair that would cross the threshold. Completeness holds for the batch under cumulative accounting; per-repair-only accounting does NOT — this is a real failure mode of a naive gate and a contribution to state explicitly.

## 7. Extensions (sketched, for the paper's "generalization" subsection)

**7.1 Non-decomposable aggregates.** For $a_j$ Lipschitz in the touched fields with constant $L_j$, $|\Delta_j(\rho)| \le L_j \cdot \|\rho(r) - r\|$ on the touched records; gate on this upper bound. Completeness preserved (never under-escalates); soundness weakened (may over-escalate). Ratios like coverage-ratio = allowance/exposure are handled by escalating when either numerator or denominator change is individually material, a conservative sufficient condition.

**7.2 Cumulative / batch materiality.** Maintain running totals $S_j = \sum_{\text{applied }k} \Delta_j(\rho_k)$. Admit $\rho_{k+1}$ only if $|S_j + \Delta_j(\rho_{k+1})| < \tau_j$ for all $j$. The first repair that would cross is escalated. This makes the gate complete against the *accumulation* attack, where many immaterial repairs conspire to a material one — the failure mode that distinguishes a serious gate from a toy one.

**7.3 Priority tiers.** Escalated repairs are ranked by $\max_j |\Delta_j(\rho)|/\tau_j$ (materiality-tiered prioritization), so human reviewers see the most consequential repairs first — the benchmark's third scoring axis.
