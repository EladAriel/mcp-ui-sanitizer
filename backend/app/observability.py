import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langfuse import get_client
from langfuse.langchain import CallbackHandler

from app.config import Settings

logger = logging.getLogger(__name__)


class Trace:
    def __init__(self, span: Any = None, handler: CallbackHandler | None = None):
        self.span = span
        self.callbacks = [handler] if handler else []

    def finish(
        self,
        *,
        output: str | None,
        validation_issues: list[dict[str, Any]],
        error: str | None = None,
    ) -> None:
        if not self.span:
            return
        try:
            self.span.update(
                output={"sanitized_code": output, "validation_issues": validation_issues},
                level="ERROR" if error else "DEFAULT",
                status_message=error,
            )
        except Exception:
            logger.warning("Could not finalize Langfuse trace", exc_info=True)


def _configured(settings: Settings) -> bool:
    return (
        settings.langfuse_enabled
        and bool(os.getenv("LANGFUSE_PUBLIC_KEY"))
        and bool(os.getenv("LANGFUSE_SECRET_KEY"))
    )


@contextmanager
def sanitization_trace(
    settings: Settings,
    *,
    request_id: str,
    source: str,
    raw_code: str,
    target_component_name: str,
    allowed_features: list[str],
) -> Iterator[Trace]:
    if not _configured(settings):
        yield Trace()
        return

    try:
        client = get_client()
        handler = CallbackHandler()
        manager = client.start_as_current_observation(
            name="clean_design_artifact",
            as_type="chain",
            input={
                "raw_code": raw_code,
                "target_component_name": target_component_name,
                "allowed_features": allowed_features,
            },
            metadata={
                "request_id": request_id,
                "source": source,
                "model": settings.llm_model,
                "environment": settings.environment,
            },
        )
        span = manager.__enter__()
    except Exception:
        logger.warning("Langfuse tracing unavailable; continuing without tracing", exc_info=True)
        yield Trace()
        return

    try:
        yield Trace(span, handler)
    except BaseException:
        manager.__exit__(*sys.exc_info())
        raise
    else:
        manager.__exit__(None, None, None)


def flush_langfuse(settings: Settings) -> None:
    if not _configured(settings):
        return
    try:
        get_client().flush()
    except Exception:
        logger.warning("Could not flush Langfuse", exc_info=True)
