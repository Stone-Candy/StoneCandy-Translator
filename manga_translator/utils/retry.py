import asyncio
import re
from typing import Any, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")

_HTTP_STATUS_RE = re.compile(r"(?:status|http)\s*(\d{3})", re.IGNORECASE)
_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}
_NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 405, 422}
_NON_RETRYABLE_MARKERS = (
    "could not find a compatible image output interface",
    "is not configured",
    "unsupported api",
    "invalid api key",
    "incorrect api key",
    "authentication failed",
    "unauthorized",
    "forbidden",
)
_RETRYABLE_MARKERS = (
    "did not contain an image",
    "did not contain image data",
    "did not contain ocr text",
    "did not contain text",
    "returned invalid json",
    "timed out",
    "timeout",
    "connection",
    "connect",
    "network",
    "temporary failure",
    "temporarily unavailable",
    "server disconnected",
    "empty reply",
    "reset by peer",
    "rate limit",
    "bad gateway",
    "service unavailable",
    "a timeout occurred",
)


def normalize_retry_attempts(attempts: Any, logger=None, default: int = -1) -> int:
    try:
        value = int(attempts)
    except (TypeError, ValueError):
        if logger is not None:
            logger.warning(
                f"Invalid attempts value '{attempts}', fallback to {default} "
                f"({'infinite' if default == -1 else 'no retry' if default == 0 else default})"
            )
        return default

    if value == -1:
        return -1
    if value < -1:
        if logger is not None:
            logger.warning(f"Invalid attempts value '{value}', fallback to 0 (no retry)")
        return 0
    return value


def resolve_total_attempts(attempts: int) -> int:
    if attempts == -1:
        return -1
    return attempts + 1


def get_retry_attempts_from_config(config: Any, logger=None, fallback: int = -1) -> int:
    if config is None:
        return normalize_retry_attempts(fallback, logger=logger, default=fallback)

    if isinstance(config, dict):
        cli_config = config.get("cli")
        if isinstance(cli_config, dict) and "attempts" in cli_config:
            return normalize_retry_attempts(cli_config.get("attempts"), logger=logger, default=fallback)
        if "attempts" in config:
            return normalize_retry_attempts(config.get("attempts"), logger=logger, default=fallback)
        return normalize_retry_attempts(fallback, logger=logger, default=fallback)

    cli_config = getattr(config, "cli", None)
    if cli_config is not None and hasattr(cli_config, "attempts"):
        return normalize_retry_attempts(getattr(cli_config, "attempts"), logger=logger, default=fallback)

    if hasattr(config, "attempts"):
        return normalize_retry_attempts(getattr(config, "attempts"), logger=logger, default=fallback)

    return normalize_retry_attempts(fallback, logger=logger, default=fallback)


def summarize_text(value: Any, limit: Optional[int] = None, empty_placeholder: str = "(empty)") -> str:
    message = " ".join(str(value).split()) if value is not None else ""
    if not message:
        return empty_placeholder
    if limit is None or len(message) <= limit:
        return message
    if limit <= 3:
        return message[:limit]
    return f"{message[: limit - 3]}..."


def summarize_exception_message(error: Exception, limit: Optional[int] = None) -> str:
    return summarize_text(error, limit=limit, empty_placeholder="")


def summarize_response_text(
    text: Any,
    limit: Optional[int] = None,
    empty_placeholder: str = "(empty)",
) -> str:
    return summarize_text(text, limit=limit, empty_placeholder=empty_placeholder)


def is_retryable_api_error(error: Exception) -> bool:
    if isinstance(error, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError)):
        return True

    message = summarize_exception_message(error).lower()
    if not message:
        return False

    if any(marker in message for marker in _NON_RETRYABLE_MARKERS):
        return False

    match = _HTTP_STATUS_RE.search(message)
    if match:
        status_code = int(match.group(1))
        if status_code in _RETRYABLE_STATUS_CODES:
            return True
        if status_code in _NON_RETRYABLE_STATUS_CODES:
            return False

    return any(marker in message for marker in _RETRYABLE_MARKERS)


async def run_with_retry(
    *,
    operation: Callable[[], Awaitable[T]],
    runtime_config: Any,
    provider_name: str,
    operation_name: str,
    logger,
    on_retry: Optional[Callable[[int, Exception], Awaitable[None]]] = None,
    retryable_error: Callable[[Exception], bool] = is_retryable_api_error,
    fallback_attempts: int = -1,
) -> T:
    retry_attempts = get_retry_attempts_from_config(
        runtime_config,
        logger=logger,
        fallback=fallback_attempts,
    )
    max_total_attempts = resolve_total_attempts(retry_attempts)
    attempt_index = 0

    while True:
        attempt_index += 1
        try:
            return await operation()
        except Exception as exc:
            if not retryable_error(exc):
                raise

            if max_total_attempts != -1 and attempt_index >= max_total_attempts:
                raise RuntimeError(
                    f"{provider_name} {operation_name} failed after {attempt_index} attempts: "
                    f"{summarize_exception_message(exc)}"
                ) from exc

            attempt_limit = "inf" if max_total_attempts == -1 else str(max_total_attempts)
            logger.warning(
                f"{provider_name}: {operation_name} failed on attempt {attempt_index}/{attempt_limit}: "
                f"{summarize_exception_message(exc)}. Retrying..."
            )

            if on_retry is not None:
                await on_retry(attempt_index, exc)

            await asyncio.sleep(min(1.0 * attempt_index, 3.0))
