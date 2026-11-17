"""Print the synthetic comparison of the two pickup orderings.

Usage: python scripts/evaluate_discovery.py [seed] [searches]
The numbers describe behaviour under the declared synthetic assumptions only; see
docs/evaluation-discovery.md before quoting them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app-backend"))

from app.domain.discovery_evaluation import (  # noqa: E402
    EVALUATION_SEED,
    SEARCH_COUNT,
    evaluate,
)

PERCENT = 100


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else EVALUATION_SEED
    searches = int(sys.argv[2]) if len(sys.argv) > 2 else SEARCH_COUNT
    report = evaluate(seed, searches)
    print(f"seed={report.seed} searches={report.searches}")
    print(f"searches with at least one collectable lot: {report.searches_with_a_collectable_lot}")
    for result in report.results:
        print(
            f"{result.method.value:14} top result collectable in "
            f"{result.collectable_top_results}/{result.searches_answered} "
            f"({result.collectable_rate * PERCENT:.1f}%)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
