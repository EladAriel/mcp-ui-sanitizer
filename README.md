# UI Design Sanitizer & MCP Pipeline

A fail-closed pre-processing pipeline for generated UI prototypes. It removes
mock state, fake event logic, runtime side effects, and unsupported features,
then exposes validated presentation code to Cursor through a stdio MCP tool.

## Architecture

```text
Cursor ──stdio MCP──┐
                   ├── SanitizationService ── Tree-sitter preflight
React ──FastAPI────┘                         ├─ LangChain model
  └────SSE progress                          ├─ Langfuse trace
                                             └─ Tree-sitter policy validation
```

The model proposes a transformation. It is not the safety boundary: malformed
or policy-violating output is rejected and never returned. Temperature zero is
repeatable, not deterministic; AST validation supplies deterministic structural
guarantees.

## Repository

- `backend/`: Python 3.12, uv, FastAPI, LangChain, Langfuse, Tree-sitter, MCP.
- `frontend/`: React, Vite, Tailwind CSS, shadcn-style primitives, diff and syntax
  views.
- `.cursor/`: stdio MCP registration and the current Cursor project rule.
- `.cursorrules`: compatibility blueprint for UI integration behavior.

## Local development

### Backend

Install [uv](https://docs.astral.sh/uv/), then:

```bash
cp backend/.env.example backend/.env
uv sync --directory backend
uv --directory backend run ui-sanitizer-api
```

The API is served at `http://127.0.0.1:8000`. Configure one provider key:

- Default: `OPENAI_API_KEY` with `gpt-5.6-luna`.
- Anthropic: set `SANITIZER_LLM_PROVIDER=anthropic`,
  `SANITIZER_LLM_MODEL=claude-haiku-4-5`, and `ANTHROPIC_API_KEY`.
- OpenRouter: set `SANITIZER_LLM_PROVIDER=openrouter`,
  `SANITIZER_LLM_MODEL=openai/gpt-4o-mini` (or another OpenRouter slug),
  and `OPENROUTER_API_KEY`. Optional attribution headers use
  `SANITIZER_OPENROUTER_HTTP_REFERER` and `SANITIZER_OPENROUTER_APP_TITLE`.

For the repository workflow UI, set `SANITIZER_WORKSPACE_ROOTS` to one or more
absolute local directories the API may read. Paths outside those roots are
rejected. Checked-in mocks for manual testing live under [`example/`](example/)
(see [`example/README.md`](example/README.md)).

Cursor model credits do not fund backend API calls. The chosen provider account
is billed directly.

### Frontend

```bash
npm install --prefix frontend
npm run dev --prefix frontend
```

Vite serves `http://localhost:5173` and proxies `/api` and `/health` to FastAPI.

### Cursor MCP

The checked-in `.cursor/mcp.json` launches:

```bash
uv --directory backend run ui-sanitizer-mcp
```

Restart Cursor after configuring provider and Langfuse environment variables.
The MCP tool contract is:

```json
{
  "raw_code": "string",
  "target_component_name": "string",
  "allowed_features": ["string"]
}
```

On success, `clean_design_artifact` returns source code only. On validation
failure it returns an MCP tool error and no partial output.

## HTTP contracts

- `POST /api/v1/sanitizations` creates a bounded asynchronous job.
- `GET /api/v1/sanitizations/{job_id}` returns status or the final result.
- `GET /api/v1/sanitizations/{job_id}/events` streams named SSE progress,
  completion, and error events.
- `GET /api/v1/repos/browse` lists files under an allowlisted local path.
- `POST /api/v1/repos/inventory` inventories a production repository target.
- `POST /api/v1/repos/save-component` writes updated JSX/TSX back to a production file.
- `POST /api/v1/workflows` starts an HTML repository sanitization workflow
  (returns sanitized HTML plus production JSX before/after for comparison).
- `GET /api/v1/workflows/{job_id}` returns workflow status or the final result.
- `GET /api/v1/workflows/{job_id}/events` streams structured execution-trace SSE.
- `GET /health/live` and `GET /health/ready` expose process/configuration health.

Jobs are in-memory with a TTL and the API is intentionally single-worker. Use a
shared queue and result store such as Redis before deploying multiple workers.
Authentication should be enforced by the internal gateway; CORS alone is not
authentication.

## Observability and privacy

When `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are present, every
sanitization creates a Langfuse trace with the source transport, model metadata,
latency, validation result, and LangChain model token usage. Prototype and
sanitized source are redacted by default; set `SANITIZER_LANGFUSE_CAPTURE_CODE=true`
only after reviewing Langfuse retention and access controls. Tracing failure does
not bypass policy validation or fail the request.

## Quality checks

```bash
uv --directory backend run ruff check .
uv --directory backend run mypy app
uv --directory backend run pytest --cov=app
npm run lint --prefix frontend
npm run test --prefix frontend
npm run build --prefix frontend
```

Normal tests use injected models and spend no model tokens. Run live provider
smoke tests separately after reviewing expected cost and data handling.

## Model cost controls

The default model is GPT-5.6 Luna for its strict structured output and
price/quality balance. Keep output limits bounded and benchmark a fixed,
adversarial fixture set against Claude Haiku 4.5 before changing the default.
Prompt caching can reduce repeated system-prompt input costs where the provider
supports it, but batch APIs do not fit the interactive SSE workflow.

## Enforcement limits

Cursor rules are instructions, not a security or merge-control boundary. For
hard enforcement, add a CI check required by branch protection that identifies
generated UI changes and verifies an auditable sanitizer result.
