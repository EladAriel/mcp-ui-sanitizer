import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent


@pytest.mark.asyncio
async def test_stdio_tool_discovery_and_invocation() -> None:
    backend = Path(__file__).parents[1]
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(backend / "tests" / "fixtures" / "mcp_test_server.py")],
        cwd=str(backend),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool = next(item for item in tools.tools if item.name == "clean_design_artifact")
            assert set(tool.inputSchema["required"]) == {
                "raw_code",
                "target_component_name",
                "allowed_features",
            }

            result = await session.call_tool(
                "clean_design_artifact",
                arguments={
                    "raw_code": """export function Greeting() {
  const [open, setOpen] = useState(false);
  return <div className="p-4">Hello</div>;
}""",
                    "target_component_name": "Greeting",
                    "allowed_features": [],
                },
            )

    assert not result.isError
    assert isinstance(result.content[0], TextContent)
    assert (
        result.content[0].text
        == """export function Greeting() {
  return <div className="p-4">Hello</div>;
}"""
    )
