import asyncio
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.schemas import CleanDesignArtifactInput
from app.service import SanitizationService

RAW = """export function Panel() {
  const [open, setOpen] = useState(false);
  return <section className="p-4">Details</section>;
}"""
SAFE = """export function Panel() {
  return <section className="p-4">Details</section>;
}"""


class StaticEngine:
    async def sanitize(
        self,
        _request: CleanDesignArtifactInput,
        *,
        callbacks: list[Any] | None = None,
    ) -> str:
        return SAFE


@pytest.mark.asyncio
async def test_rest_job_and_sse_contract() -> None:
    settings = Settings(llm_provider="fake", langfuse_enabled=False)
    service = SanitizationService(settings, StaticEngine())
    app = create_app(settings, service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        accepted = await client.post(
            "/api/v1/sanitizations",
            json={
                "raw_code": RAW,
                "target_component_name": "Panel",
                "allowed_features": [],
            },
        )
        assert accepted.status_code == 202
        contract = accepted.json()

        for _ in range(20):
            result = await client.get(contract["result_url"])
            if result.json()["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.01)

        assert result.json()["status"] == "completed"
        assert result.json()["sanitized_code"] == SAFE

        events = await client.get(contract["events_url"])
        assert events.status_code == 200
        assert events.headers["content-type"].startswith("text/event-stream")
        assert "event: progress" in events.text
        assert "event: complete" in events.text
        assert '"stage":"done"' in events.text


@pytest.mark.asyncio
async def test_unknown_job_returns_stable_error() -> None:
    settings = Settings(llm_provider="fake", langfuse_enabled=False)
    app = create_app(settings, SanitizationService(settings, StaticEngine()))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/sanitizations/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "JOB_EXPIRED"
