# Procurement strategy comparison

The application generates four heuristic allocation plans: `cheapest`,
`lowest_risk`, `fastest`, and `weighted_risk_cost`. The `pareto_comparison`
result compares those candidates by total estimated cost, late-delivery risk,
delivery lead time, and material shortage. A candidate is dominated only when
another candidate is no worse in every objective and strictly better in at least
one. Equal candidates can remain on the front with their strategy identities.

This is a comparison of four candidates, not an NSGA-II evolutionary search or
a guarantee of globally optimal procurement. The default allocation shown and
saved for `pareto_comparison` is the balanced `weighted_risk_cost` plan. Users
can select any of the four base strategies to save a different allocation.

Zero risk and zero-day delivery are valid objective values. For comparison
only, unknown risk is treated as 1.0 and unknown delivery time as unbounded;
missing values remain `null` in responses. A reported zero empirical delay rate
describes the observed sample and is not a guarantee of future on-time delivery.

## API compatibility

`POST /api/procurement/optimize` returns `alternatives` containing the four base
strategies, `pareto_comparison`, and the legacy `nsga_ii` alias. The comparison
includes `pareto_front_solutions`, all four `pareto_synthesis.tradeoff_points`,
the nondominated strategy names, and the default `allocation_strategy`.

New clients should submit `pareto_comparison` to
`POST /api/procurement/plans`. Existing clients and saved plans can continue to
use `nsga_ii`; its allocation behavior is preserved and its response carries
`deprecated_alias_for: "pareto_comparison"`. The top-level `nsga_ii.available`
flag is false because that algorithm is not implemented. Pareto comparison
availability is reported separately under `pareto_comparison`.

The same frontier calculation is shared by the scenario solver service and
the application's procurement endpoints. This change does not rewrite existing
plans, model registry records, research artifacts, or other database records.
Newly seeded registry metadata describes the heuristic method accurately;
historical registry entries remain historical.

## Validation

From `backend`, run `.venv/bin/python -m pytest -q`. Optimizer regressions use
in-memory SQLite, and API tests use temporary databases. Coverage includes zero
and missing risk, same-day delivery, shortages, and creation, approval, and
ordering through both the canonical identifier and legacy alias.

From `frontend`, run `npm run build` to type-check and build the comparison UI.
