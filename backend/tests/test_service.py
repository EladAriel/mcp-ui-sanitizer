from typing import Any

import pytest

from app.config import Settings
from app.schemas import CleanDesignArtifactInput, ErrorCode
from app.service import SanitizationError, SanitizationService

RAW = """export function Banner() {
  const [open, setOpen] = useState(false);
  return <div className="p-4">Welcome</div>;
}"""

SAFE = """export function Banner() {
  return <div className="p-4">Welcome</div>;
}"""


class StaticEngine:
    def __init__(self, output: str):
        self.output = output

    async def sanitize(
        self,
        _request: CleanDesignArtifactInput,
        *,
        callbacks: list[Any] | None = None,
        repair_instruction: str = "",
    ) -> str:
        return self.output

    async def merge_into_component(
        self,
        *,
        production_jsx: str,
        sanitized_html: str,
        target_component_name: str,
        allowed_features: list[str],
        callbacks: list[Any] | None = None,
        repair_instruction: str = "",
    ) -> str:
        return self.output


@pytest.mark.asyncio
async def test_service_reports_progress_and_returns_validated_code() -> None:
    settings = Settings(llm_provider="fake", langfuse_enabled=False)
    service = SanitizationService(settings, StaticEngine(SAFE))
    stages: list[str] = []

    async def progress(stage: Any, _message: str) -> None:
        stages.append(stage.value)

    result = await service.clean(
        CleanDesignArtifactInput(
            raw_code=RAW,
            target_component_name="Banner",
            allowed_features=[],
        ),
        source="test",
        progress=progress,
    )

    assert result == SAFE
    assert stages == [
        "parsing_ast",
        "stripping_mock_logic",
        "llm_processing",
        "validating_output",
    ]


@pytest.mark.asyncio
async def test_service_never_returns_policy_violating_output() -> None:
    settings = Settings(llm_provider="fake", langfuse_enabled=False)
    service = SanitizationService(settings, StaticEngine("export function Other() {}"))

    with pytest.raises(SanitizationError) as captured:
        await service.clean(
            CleanDesignArtifactInput(
                raw_code=RAW,
                target_component_name="Banner",
                allowed_features=[],
            ),
            source="test",
        )
    assert captured.value.code is ErrorCode.POLICY_VIOLATION
