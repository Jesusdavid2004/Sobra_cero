import json
import subprocess
import sys
from pathlib import Path

from app.application.scanner_dto import RunResult
from app.domain.collection import EXECUTION_TIMEOUT_SECONDS, ExecutionStatus, StopReason
from app.domain.exceptions import SourceNotRunnableError

BACKEND_ROOT = Path(__file__).resolve().parents[2]
NO_EXECUTION = 0


class SubprocessSourceRunner:
    """Start `python -m scraper.run` so the web process never imports Scrapy or its reactor."""

    def run(self, source_key: str, trigger: str, user_id: int | None) -> RunResult:
        command = [sys.executable, "-m", "scraper.run", "--source", source_key, "--trigger", trigger]
        if user_id is not None:
            command += ["--user-id", str(user_id)]
        try:
            completed = subprocess.run(
                command,
                cwd=BACKEND_ROOT,
                capture_output=True,
                text=True,
                timeout=EXECUTION_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return self._failed(StopReason.TIMEOUT, "The run exceeded its time limit")
        lines = completed.stdout.strip().splitlines()
        if not lines:
            return self._failed(StopReason.CRASHED, "The run produced no result")
        payload = json.loads(lines[-1])
        if payload.get("status") == "refused":
            raise SourceNotRunnableError(str(payload.get("error", "refused")))
        return RunResult(
            execution_id=int(payload["execution_id"]),
            status=str(payload["status"]),
            accepted=int(payload["accepted"]),
            rejected=int(payload["rejected"]),
            pending=int(payload["pending"]),
            duplicates=int(payload["duplicates"]),
            stop_reason=str(payload["stop_reason"]),
            error=str(payload["error"]),
        )

    @staticmethod
    def _failed(reason: StopReason, message: str) -> RunResult:
        return RunResult(NO_EXECUTION, ExecutionStatus.FAILED.value, 0, 0, 0, 0, reason.value, message)
