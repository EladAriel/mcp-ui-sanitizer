import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
from typing import Any

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app.config import Settings

logger = logging.getLogger(__name__)
REDACTED = "[REDACTED]"
SENSITIVE_FIELD_NAMES = frozenset(
    {"api_key", "apikey", "authorization", "password", "secret", "token"}
)


class Trace:
    def __init__(
        self,
        span: Any = None,
        handler: CallbackHandler | None = None,
        trace_input: dict[str, Any] | None = None,
        capture_code: bool = False,
    ):
        self.span = span
        self.callbacks = [handler] if handler else []
        self.trace_input = trace_input
        self.capture_code = capture_code

    def finish(
        self,
        *,
        output: str | None,
        validation_issues: list[dict[str, Any]],
        error: str | None = None,
    ) -> None:
        if not self.span:
            return
        trace_output: dict[str, Any] = {
            "result": "error" if error else "success",
            "sanitized_artifact": _artifact_value(output, self.capture_code) if output else None,
            "validation_issues": validation_issues,
        }
        try:
            self.span.update(
                output=trace_output,
                level="ERROR" if error else "DEFAULT",
                status_message=error,
            )
            self.span.set_trace_io(input=self.trace_input, output=trace_output)
        except Exception:
            logger.warning("Could not finalize Langfuse trace", exc_info=True)


def _artifact_value(
    code: str | None, capture_code: bool
) -> str | dict[str, int | str] | None:
    if code is None:
        return None
    if capture_code:
        return code
    return {
        "bytes": len(code.encode()),
        "sha256": sha256(code.encode()).hexdigest(),
    }


def _mask_sensitive_data(*, data: Any, capture_code: bool, **_: Any) -> Any:
    """Redact credential fields and optionally all traced model content."""
    if not capture_code and isinstance(data, str):
        return REDACTED
    if isinstance(data, dict):
        return {
            key: (
                REDACTED
                if key.lower() in SENSITIVE_FIELD_NAMES
                else _mask_sensitive_data(data=value, capture_code=capture_code)
            )
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_mask_sensitive_data(data=value, capture_code=capture_code) for value in data]
    if isinstance(data, tuple):
        return tuple(_mask_sensitive_data(data=value, capture_code=capture_code) for value in data)
    return data


def _langfuse_client(settings: Settings) -> Langfuse:
    return Langfuse(
        environment=settings.environment,
        mask=partial(_mask_sensitive_data, capture_code=settings.langfuse_capture_code),
    )


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
        client = _langfuse_client(settings)
        handler = CallbackHandler()
        trace_input = {
            "raw_artifact": _artifact_value(raw_code, settings.langfuse_capture_code),
            "target_component_name": target_component_name,
            "allowed_features": allowed_features,
        }
        manager = client.start_as_current_observation(
            name="sanitize-ui-artifact",
            as_type="chain",
            input=trace_input,
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
        yield Trace(span, handler, trace_input, settings.langfuse_capture_code)
    except BaseException:
        manager.__exit__(*sys.exc_info())
        raise
    else:
        manager.__exit__(None, None, None)


def flush_langfuse(settings: Settings) -> None:
    if not _configured(settings):
        return
    try:
        _langfuse_client(settings).flush()
    except Exception:
        logger.warning("Could not flush Langfuse", exc_info=True)
