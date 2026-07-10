from typing import Any

from app.observability import REDACTED, Trace, _artifact_value, _mask_sensitive_data


class FakeSpan:
    def __init__(self) -> None:
        self.updated: dict[str, Any] | None = None
        self.trace_io: dict[str, Any] | None = None

    def update(self, **kwargs: Any) -> None:
        self.updated = kwargs

    def set_trace_io(self, **kwargs: Any) -> None:
        self.trace_io = kwargs


def test_artifact_value_uses_a_digest_when_code_capture_is_disabled() -> None:
    assert _artifact_value("const token = 'secret';", capture_code=False) == {
        "bytes": 23,
        "sha256": "05dfd7b3822c2de70afa272f22ac5bb25190d8c596b4540aa5607e5c9a802f86",
    }


def test_mask_removes_model_content_and_credentials_by_default() -> None:
    masked = _mask_sensitive_data(
        data={"raw_code": "export const secret = true", "api_key": "key"},
        capture_code=False,
    )

    assert masked == {"raw_code": REDACTED, "api_key": REDACTED}


def test_mask_allows_opted_in_code_but_never_credentials() -> None:
    masked = _mask_sensitive_data(
        data={"raw_code": "export const panel = true", "api_key": "key"},
        capture_code=True,
    )

    assert masked == {"raw_code": "export const panel = true", "api_key": REDACTED}


def test_trace_sets_root_input_output_and_error_status() -> None:
    span = FakeSpan()
    trace = Trace(span=span, trace_input={"source": "mcp"}, capture_code=False)

    trace.finish(
        output="export function Panel() {}",
        validation_issues=[],
        error="policy rejected output",
    )

    assert span.updated == {
        "output": {
            "result": "error",
            "sanitized_artifact": {
                "bytes": 26,
                "sha256": "ed99e7e933f1d2acadcf91cc05fec3d2912eba99a04665b1c67553edad590402",
            },
            "validation_issues": [],
        },
        "level": "ERROR",
        "status_message": "policy rejected output",
    }
    assert span.trace_io == {"input": {"source": "mcp"}, "output": span.updated["output"]}
