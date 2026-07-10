# Backend

FastAPI, LangChain, Langfuse, Tree-sitter, and stdio MCP implementation for the
UI Design Sanitizer.

```bash
cp .env.example .env
uv sync
uv run ui-sanitizer-api
```

Run the MCP server with `uv run ui-sanitizer-mcp`. Protocol messages use stdout;
application diagnostics use stderr.