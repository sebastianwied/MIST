"""Manage broker and agent subprocesses."""

from __future__ import annotations

import logging
import signal
import socket
import subprocess
import time
from pathlib import Path

from mist_core.transport import DEFAULT_SOCKET_PATH

log = logging.getLogger(__name__)

BROKER_POLL_INTERVAL = 0.2
BROKER_POLL_TIMEOUT = 5.0


class ProcessManager:
    """Start and stop broker/agent subprocesses."""

    def __init__(self, socket_path: Path | None = None) -> None:
        self._socket_path = socket_path or DEFAULT_SOCKET_PATH
        self._processes: list[subprocess.Popen] = []

    def broker_running(self) -> bool:
        """Check whether the broker is listening on its socket."""
        if not self._socket_path.exists():
            return False
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect(str(self._socket_path))
            s.close()
            return True
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            return False

    def start_broker(self) -> None:
        """Start the broker as a subprocess and wait until it is ready."""
        args = ["mist-broker", "--socket-path", str(self._socket_path)]
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._processes.append(proc)
        log.info("started broker (pid %d)", proc.pid)

        deadline = time.monotonic() + BROKER_POLL_TIMEOUT
        while time.monotonic() < deadline:
            if self.broker_running():
                log.info("broker ready")
                return
            if proc.poll() is not None:
                raise RuntimeError(
                    f"broker exited immediately with code {proc.returncode}"
                )
            time.sleep(BROKER_POLL_INTERVAL)

        raise TimeoutError("broker did not become ready in time")

    def start_agent(self, command: str) -> None:
        """Start an agent subprocess."""
        args = [command, "--socket", str(self._socket_path)]
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._processes.append(proc)
        log.info("started agent %s (pid %d)", command, proc.pid)

    def shutdown(self) -> None:
        """Terminate all managed subprocesses."""
        for proc in reversed(self._processes):
            if proc.poll() is None:
                log.info("terminating pid %d", proc.pid)
                proc.send_signal(signal.SIGTERM)

        for proc in self._processes:
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                log.warning("killing pid %d", proc.pid)
                proc.kill()

        self._processes.clear()
