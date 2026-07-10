import asyncio
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.repos import RepoAccessError, RepositoryAccess
from app.schemas import CleanDesignArtifactInput, WorkflowStep
from app.service import SanitizationService

RAW_HTML = """<!doctype html>
<html>
  <body>
    <section>
      <h1>Order summary</h1>
      <p>$99</p>
      <button onclick="alert('pay')">Checkout</button>
    </section>
  </body>
</html>
"""

SAFE_HTML = """<!doctype html>
<html>
  <body>
    <section>
      <h1>Order summary</h1>
      <p>$99</p>
      <button>Checkout</button>
    </section>
  </body>
</html>
"""

PROD_JSX = """export function CheckoutCard() {
  return (
    <section>
      <h1>Order summary</h1>
      <button type="button">Checkout</button>
    </section>
  );
}
"""

AFTER_JSX = """export function CheckoutCard() {
  return (
    <section>
      <h1>Order summary</h1>
      <p>$99</p>
      <button type="button">Checkout</button>
    </section>
  );
}
"""


class StaticEngine:
    async def sanitize(
        self,
        _request: CleanDesignArtifactInput,
        *,
        callbacks: list[Any] | None = None,
        repair_instruction: str = "",
    ) -> str:
        return SAFE_HTML

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
        return AFTER_JSX


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    production = tmp_path / "prod"
    design = tmp_path / "design"
    production.mkdir()
    design.mkdir()
    (production / "CheckoutCard.jsx").write_text(PROD_JSX, encoding="utf-8")
    (design / "checkout.html").write_text(RAW_HTML, encoding="utf-8")
    (design / "notes.txt").write_text("not html", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.html").write_text("<html><body>nope</body></html>", encoding="utf-8")
    return tmp_path


def test_path_containment_rejects_outside_roots(workspace: Path) -> None:
    settings = Settings(
        llm_provider="fake",
        langfuse_enabled=False,
        workspace_roots=[str(workspace / "prod")],
    )
    repos = RepositoryAccess(settings)
    with pytest.raises(RepoAccessError, match="outside the configured workspace roots"):
        repos.resolve_path(str(workspace / "outside" / "secret.html"))


def test_browse_html_only_and_denied_files(workspace: Path) -> None:
    settings = Settings(
        llm_provider="fake",
        langfuse_enabled=False,
        workspace_roots=[str(workspace)],
    )
    repos = RepositoryAccess(settings)
    listed = repos.browse(str(workspace / "design"), html_only=True)
    names = {entry.name for entry in listed.entries}
    assert "checkout.html" in names
    assert "notes.txt" not in names


def test_html_only_rejection_for_non_html_design(workspace: Path) -> None:
    settings = Settings(
        llm_provider="fake",
        langfuse_enabled=False,
        workspace_roots=[str(workspace)],
    )
    repos = RepositoryAccess(settings)
    with pytest.raises(RepoAccessError, match="HTML files"):
        repos.load_design_html(str(workspace / "design"), "notes.txt")


def test_save_component_writes_under_roots(workspace: Path) -> None:
    settings = Settings(
        llm_provider="fake",
        langfuse_enabled=False,
        workspace_roots=[str(workspace)],
    )
    repos = RepositoryAccess(settings)
    path, nbytes = repos.save_component(
        str(workspace / "prod"),
        "CheckoutCard.jsx",
        AFTER_JSX,
    )
    assert path.name == "CheckoutCard.jsx"
    assert path.read_text(encoding="utf-8") == AFTER_JSX
    assert nbytes == len(AFTER_JSX.encode())


def test_save_component_rejects_outside_roots(workspace: Path) -> None:
    settings = Settings(
        llm_provider="fake",
        langfuse_enabled=False,
        workspace_roots=[str(workspace / "prod")],
    )
    repos = RepositoryAccess(settings)
    with pytest.raises(RepoAccessError, match="outside the configured workspace roots"):
        repos.save_component(
            str(workspace / "design"),
            "checkout.html",
            AFTER_JSX,
        )


@pytest.mark.asyncio
async def test_workflow_event_order_and_result_contract(workspace: Path) -> None:
    settings = Settings(
        llm_provider="fake",
        langfuse_enabled=False,
        workspace_roots=[str(workspace)],
    )
    service = SanitizationService(settings, StaticEngine())
    app = create_app(settings, service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        inventory = await client.post(
            "/api/v1/repos/inventory",
            json={
                "production_repo_path": str(workspace / "prod"),
                "target_file_path": "CheckoutCard.jsx",
            },
        )
        assert inventory.status_code == 200
        assert inventory.json()["target_component_name"] == "CheckoutCard"
        assert "Checkout action" in inventory.json()["suggested_features"]

        accepted = await client.post(
            "/api/v1/workflows",
            json={
                "production_repo_path": str(workspace / "prod"),
                "design_repo_path": str(workspace / "design"),
                "design_html_path": "checkout.html",
                "target_file_path": "CheckoutCard.jsx",
                "target_component_name": "CheckoutCard",
                "allowed_features": ["Checkout action"],
            },
        )
        assert accepted.status_code == 202
        contract = accepted.json()

        for _ in range(40):
            result = await client.get(contract["result_url"])
            if result.json()["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.02)

        body = result.json()
        assert body["status"] == "completed", body
        assert body["raw_html"] == RAW_HTML
        assert body["sanitized_html"] == SAFE_HTML
        assert body["production_jsx_before"] == PROD_JSX
        assert body["production_jsx_after"] == AFTER_JSX
        assert body["explanation"]
        assert "merged presentation" in body["explanation"]
        assert body["design_html_path"].endswith("checkout.html")

        saved = await client.post(
            "/api/v1/repos/save-component",
            json={
                "production_repo_path": str(workspace / "prod"),
                "target_file_path": "CheckoutCard.jsx",
                "source": AFTER_JSX,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["bytes_written"] == len(AFTER_JSX.encode())
        assert (workspace / "prod" / "CheckoutCard.jsx").read_text(encoding="utf-8") == AFTER_JSX

        events = await client.get(contract["events_url"])
        assert events.status_code == 200
        assert "event: progress" in events.text
        assert "event: complete" in events.text
        assert f'"step":"{WorkflowStep.VALIDATING_REPOS.value}"' in events.text
        assert f'"step":"{WorkflowStep.INVOKING_SANITIZER.value}"' in events.text
        assert f'"step":"{WorkflowStep.MERGING_INTO_JSX.value}"' in events.text
        assert f'"step":"{WorkflowStep.DONE.value}"' in events.text
        assert '"summary"' in events.text
        assert '"timestamp"' in events.text


@pytest.mark.asyncio
async def test_workflow_fails_for_path_outside_roots(workspace: Path) -> None:
    settings = Settings(
        llm_provider="fake",
        langfuse_enabled=False,
        workspace_roots=[str(workspace / "prod")],
    )
    app = create_app(settings, SanitizationService(settings, StaticEngine()))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        accepted = await client.post(
            "/api/v1/workflows",
            json={
                "production_repo_path": str(workspace / "prod"),
                "design_repo_path": str(workspace / "design"),
                "design_html_path": "checkout.html",
                "target_file_path": "CheckoutCard.jsx",
                "target_component_name": "CheckoutCard",
                "allowed_features": [],
            },
        )
        contract = accepted.json()
        for _ in range(40):
            result = await client.get(contract["result_url"])
            if result.json()["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.02)
        body = result.json()
        assert body["status"] == "failed"
        assert body["error"]["code"] == "INVALID_INPUT"
