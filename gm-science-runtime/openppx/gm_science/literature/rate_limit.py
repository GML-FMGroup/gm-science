"""Process-local request pacing for literature providers."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class SourceRateLimiter:
    """Enforce a minimum interval between requests to each source."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.clock = clock
        self.sleep = sleep
        self._last_request: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, source: str, min_interval_seconds: float) -> None:
        """Wait for the source interval and record the new request time."""

        interval = max(0.0, float(min_interval_seconds))
        with self._lock:
            now = self.clock()
            last_request = self._last_request.get(source)
            if last_request is not None:
                remaining = interval - (now - last_request)
                if remaining > 0:
                    self.sleep(remaining)
            self._last_request[source] = self.clock()
