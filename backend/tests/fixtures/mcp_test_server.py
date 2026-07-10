from typing import Any

from app.config import Settings
from app.mcp_server import create_mcp
from app.schemas import CleanDesignArtifactInput
from app.service import SanitizationService


class StaticEngine:
    async def sanitize(
        self,
        request: CleanDesignArtifactInput,
        *,
        callbacks: list[Any] | None = None,
        repair_instruction: str = "",
    ) -> str:
        return f"""export function {request.target_component_name}() {{
  return <div className="p-4">Hello</div>;
}}"""

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
        return f"""export function {target_component_name}() {{
  return <div className="p-4">Hello</div>;
}}"""


settings = Settings(llm_provider="fake", langfuse_enabled=False)
service = SanitizationService(settings, StaticEngine())
create_mcp(service).run(transport="stdio")
