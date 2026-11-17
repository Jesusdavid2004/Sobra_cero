"""Entry point of the rescue analysis gRPC service (stateless, no database access)."""

import logging
import os
import signal

from app.infrastructure.analysis.local_analyzer import LocalRescueAnalyzer
from app.infrastructure.analysis.server import build_server

DEFAULT_PORT = "50051"
SHUTDOWN_GRACE_SECONDS = 5

logger = logging.getLogger("rescue-analysis")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    token = os.environ.get("ANALYSIS_SHARED_TOKEN", "")
    if not token:
        raise SystemExit("ANALYSIS_SHARED_TOKEN is required")
    port = os.environ.get("PORT", DEFAULT_PORT)
    server = build_server(LocalRescueAnalyzer(), token)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("Rescue analysis service listening on port %s", port)
    signal.signal(signal.SIGTERM, lambda *_: server.stop(SHUTDOWN_GRACE_SECONDS))
    server.wait_for_termination()


if __name__ == "__main__":
    main()
