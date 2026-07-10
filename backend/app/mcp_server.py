import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.observability import flush_langfuse
from app.schemas import CleanDesignArtifactInput
from app.service import SanitizationError, SanitizationService

logger = logging.getLogger(__name__)


def create_mcp(service: SanitizationService | None = None) -> FastMCP[None]:
    sanitizer = service or SanitizationService()
    server = FastMCP(
        "UI Design Sanitizer",
        instructions=(
            "Sanitize generated UI artifacts before integrating their presentation into an "
            "application. The tool fails closed and never returns unvalidated partial output."
        ),
        log_level="WARNING",
    )

    @server.tool(
        name="clean_design_artifact",
        description=(
            "Remove mock logic, hallucinated states, fake handlers, and non-allowlisted "
            "features from a UI artifact. Returns validated presentation source only."
        ),
    )
    async def clean_design_artifact(
        raw_code: str,
        target_component_name: str,
        allowed_features: list[str],
    ) -> str:
        try:
            request = CleanDesignArtifactInput(
                raw_code=raw_code,
                target_component_name=target_component_name,
                allowed_features=allowed_features,
            )
            return await sanitizer.clean(request, source="mcp")
        except ValidationError as exc:
            raise ToolError(f"INVALID_INPUT: {exc}") from exc
        except SanitizationError as exc:
            details = "; ".join(issue.message for issue in exc.issues[:5])
            suffix = f" Details: {details}" if details else ""
            raise ToolError(f"{exc.code}: {exc}{suffix}") from exc

    return server


mcp = create_mcp()


def run() -> None:
    settings: Settings = get_settings()
    logging.basicConfig(level=logging.INFO)
    try:
        mcp.run(transport="stdio")
    finally:
        flush_langfuse(settings)


if __name__ == "__main__":
    run()
