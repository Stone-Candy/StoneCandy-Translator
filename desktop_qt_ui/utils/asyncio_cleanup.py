"""Helpers for shutting down temporary asyncio event loops safely."""

import asyncio
import contextlib
import logging
from typing import Optional


def shutdown_event_loop(
    loop: Optional[asyncio.AbstractEventLoop],
    *,
    logger: Optional[logging.Logger] = None,
    label: str = "asyncio event loop",
    cancel_timeout: float = 1.0,
) -> None:
    """Cancel pending tasks and close a temporary event loop cleanly."""
    if loop is None:
        return

    try:
        if loop.is_closed():
            return

        pending = [task for task in asyncio.all_tasks(loop=loop) if not task.done()]
        for task in pending:
            task.cancel()

        if pending:
            try:
                loop.run_until_complete(
                    asyncio.wait_for(
                        asyncio.gather(*pending, return_exceptions=True),
                        timeout=cancel_timeout,
                    )
                )
            except Exception as exc:
                if logger is not None:
                    logger.warning(f"{label} pending task cleanup failed: {exc}")

        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as exc:
            if logger is not None:
                logger.warning(f"{label} async generator shutdown failed: {exc}")

        shutdown_executor = getattr(loop, "shutdown_default_executor", None)
        if shutdown_executor is not None:
            try:
                loop.run_until_complete(shutdown_executor())
            except Exception as exc:
                if logger is not None:
                    logger.warning(f"{label} default executor shutdown failed: {exc}")
    finally:
        with contextlib.suppress(Exception):
            asyncio.set_event_loop(None)
        try:
            loop.close()
        except Exception as exc:
            if logger is not None:
                logger.warning(f"{label} close failed: {exc}")
