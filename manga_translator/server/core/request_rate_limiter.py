from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._attempts = defaultdict(deque)
        self._lock = Lock()

    def _prune(
        self,
        key: str,
        now: datetime,
        window: timedelta,
    ) -> deque:
        attempts = self._attempts.get(key)
        if attempts is None:
            return deque()
        cutoff = now - window
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if not attempts:
            self._attempts.pop(key, None)
        return attempts

    def check(
        self,
        key: str,
        max_attempts: int,
        window: timedelta,
    ) -> tuple[bool, int]:
        with self._lock:
            now = datetime.now(timezone.utc)
            attempts = self._prune(key, now, window)
            if len(attempts) >= max_attempts:
                retry_after = int((attempts[0] + window - now).total_seconds())
                return False, max(1, retry_after)
            return True, 0

    def record(
        self,
        key: str,
        max_attempts: int,
        window: timedelta,
    ) -> int:
        with self._lock:
            now = datetime.now(timezone.utc)
            attempts = self._prune(key, now, window)
            if key not in self._attempts:
                self._attempts[key] = attempts
            attempts.append(now)
            if len(attempts) >= max_attempts:
                retry_after = int((attempts[0] + window - now).total_seconds())
                return max(1, retry_after)
            return 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)
