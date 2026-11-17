# Evaluation: ordering lots by distance or by feasibility

Question: for one pickup per search, how often is the lot placed first actually collectable by
the customer within their window, when lots are ordered **by distance only** versus **by
feasibility** (pickup window, budget, stock, category and distance limit)?

This is a simulation with declared assumptions. It does not measure real demand, real travel
times or real food waste, and it must not be quoted as a reduction of waste.

## Method

- Code: `app-backend/app/domain/discovery_evaluation.py`, run with
  `python scripts/evaluate_discovery.py [seed] [searches]`. Tests pin that it is reproducible.
- Each search draws 30 open lots and one customer from a square of about 0.1 degrees around a
  fixed point, with a seeded random generator. Ranges (all in the module as constants):
  lots close in 15 to 360 minutes, hold 1 to 10 portions, cost 5 to 30 before a 10 to 50 %
  discount; the customer's window starts in 0 to 60 minutes and lasts 30 to 180 minutes, wants
  1 to 3 portions, has a budget of 10 to 40 and accepts up to 10 km.
- Distance is straight-line (haversine). Travel time is distance divided by a single declared
  average speed of 20 km/h. Both are approximations.
- Only searches with at least one collectable lot are compared (about 91 to 94 % of searches).
- Orderings under comparison:
  - `distance_only`: nearest first, ignoring every other constraint (the baseline).
  - `feasibility`: keeps only lots that can be collected; those closing soonest first, then the
    nearest.
- Metric: share of those searches where the first result is collectable.

## Result

| Seed | Searches compared | `distance_only` first result collectable | `feasibility` first result collectable |
| --- | --- | --- | --- |
| 20261110 (default) | 938 | 517 (55.1 %) | 938 (100 %) |
| 1 | 922 | 465 (50.4 %) | 922 (100 %) |
| 2 | 935 | 531 (56.8 %) | 935 (100 %) |
| 3 | 913 | 527 (57.7 %) | 913 (100 %) |

## How to read it

- The 100 % is true by construction: the feasibility ordering drops every lot that cannot be
  collected, so its first result is collectable whenever one exists. It is not a discovery.
- The informative number is the baseline: under these assumptions, a distance-only list puts a
  lot the customer cannot collect first in roughly 42 to 50 % of searches.
- The result depends on the ranges above. Denser shops, longer windows or higher budgets would
  shrink the gap; shorter windows would widen it. A sensitivity sweep over these ranges has not
  been run.
- It says nothing about whether customers prefer the second list, nor about waste.

## Not measured

Real pickup rates, time to acceptance, no-shows, fairness between receivers, usability of the
search, and any real-world waste reduction. These need a pilot with participants.
