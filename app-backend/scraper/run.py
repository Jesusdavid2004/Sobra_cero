"""Command line entry point: `python -m scraper.run --source <key>`.

Prints one JSON line with the run summary. The web process starts this as a subprocess.
"""

import argparse
import json
import sys

from app.db import SessionLocal
from app.domain.collection import ExecutionStatus, Trigger
from app.domain.exceptions import SourceNotRunnableError
from scraper.runner import run_source

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNKNOWN_SOURCE = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one collection source")
    parser.add_argument("--source", required=True, help="key of the registered source")
    parser.add_argument("--trigger", choices=[trigger.value for trigger in Trigger], default=Trigger.MANUAL.value)
    parser.add_argument("--user-id", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        summary = run_source(args.source, Trigger(args.trigger), args.user_id, SessionLocal)
    except SourceNotRunnableError as error:
        sys.stdout.write(json.dumps({"status": "refused", "error": str(error)}) + "\n")
        return EXIT_UNKNOWN_SOURCE
    sys.stdout.write(json.dumps(summary.as_dict()) + "\n")
    return EXIT_FAILED if summary.status == ExecutionStatus.FAILED.value else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
