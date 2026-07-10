"""Secure local repository access constrained to configured workspace roots."""

from __future__ import annotations

import re
from pathlib import Path

from app.ast_policy import SourceLanguage, detect_language, inventory_artifact
from app.config import Settings
from app.schemas import (
    ErrorCode,
    InventoryResult,
    RepoBrowseResult,
    RepoEntry,
    ValidationIssue,
)

_SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".turbo",
    "coverage",
}
_COMPONENT_NAME = re.compile(
    r"(?:export\s+(?:default\s+)?(?:function|const|class)\s+|function\s+)([A-Z][A-Za-z0-9_]*)"
)
_MAX_LIST_ENTRIES = 500


class RepoAccessError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INVALID_INPUT,
        issues: list[ValidationIssue] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.issues = issues or []


class RepositoryAccess:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.roots = [Path(root) for root in settings.workspace_roots]

    def require_roots(self) -> None:
        if not self.roots:
            raise RepoAccessError(
                "No workspace roots are configured. Set SANITIZER_WORKSPACE_ROOTS."
            )

    def resolve_path(self, raw_path: str, *, must_exist: bool = True) -> Path:
        self.require_roots()
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise RepoAccessError("Repository paths must be absolute.")
        try:
            resolved = candidate.resolve(strict=must_exist)
        except FileNotFoundError as exc:
            raise RepoAccessError(f"Path does not exist: {raw_path}") from exc
        except OSError as exc:
            raise RepoAccessError(f"Path is not readable: {raw_path}") from exc

        if not self._is_under_roots(resolved):
            raise RepoAccessError(
                "Path is outside the configured workspace roots.",
            )
        if must_exist and not resolved.exists():
            raise RepoAccessError(f"Path does not exist: {raw_path}")
        return resolved

    def resolve_under_repo(self, repo_path: str, relative_or_absolute: str) -> Path:
        repo = self.resolve_path(repo_path, must_exist=True)
        if not repo.is_dir():
            raise RepoAccessError(f"Repository path is not a directory: {repo_path}")

        candidate = Path(relative_or_absolute).expanduser()
        if not candidate.is_absolute():
            candidate = repo / candidate
        resolved = self.resolve_path(str(candidate), must_exist=True)
        try:
            resolved.relative_to(repo)
        except ValueError as exc:
            raise RepoAccessError(
                "File path must remain inside the selected repository.",
            ) from exc
        return resolved

    def browse(self, raw_path: str, *, html_only: bool = False) -> RepoBrowseResult:
        path = self.resolve_path(raw_path, must_exist=True)
        if not path.is_dir():
            raise RepoAccessError(f"Browse path is not a directory: {raw_path}")

        entries: list[RepoEntry] = []
        try:
            children = sorted(
                path.iterdir(),
                key=lambda item: (not item.is_dir(), item.name.lower()),
            )
        except OSError as exc:
            raise RepoAccessError(f"Directory is not readable: {raw_path}") from exc

        for child in children:
            if len(entries) >= _MAX_LIST_ENTRIES:
                break
            if child.name.startswith(".") or child.name in _SKIP_DIR_NAMES:
                continue
            try:
                # Resolve without following a final symlink that escapes roots.
                if child.is_symlink():
                    target = child.resolve(strict=False)
                    if not self._is_under_roots(target):
                        continue
                if child.is_dir():
                    entries.append(
                        RepoEntry(name=child.name, path=str(child.resolve()), kind="directory")
                    )
                elif child.is_file():
                    if html_only and child.suffix.lower() not in {".html", ".htm"}:
                        continue
                    entries.append(
                        RepoEntry(
                            name=child.name,
                            path=str(child.resolve()),
                            kind="file",
                            size=child.stat().st_size,
                        )
                    )
            except OSError:
                continue

        return RepoBrowseResult(root=str(path), path=str(path), entries=entries)

    def read_text_file(self, path: Path) -> str:
        if not path.is_file():
            raise RepoAccessError(f"Expected a file: {path}")
        size = path.stat().st_size
        if size > self.settings.max_code_bytes:
            raise RepoAccessError(
                f"File exceeds the {self.settings.max_code_bytes}-byte limit.",
            )
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RepoAccessError("File is not valid UTF-8 text.") from exc
        except OSError as exc:
            raise RepoAccessError(f"File is not readable: {path}") from exc

    def inventory_production(
        self,
        production_repo_path: str,
        target_file_path: str,
    ) -> InventoryResult:
        target = self.resolve_under_repo(production_repo_path, target_file_path)
        source = self.read_text_file(target)
        language = detect_language(source)
        inventory = inventory_artifact(source, language)
        component_name = _infer_component_name(source, target)
        suggested = _suggest_features(source, inventory.interactive_tags)
        return InventoryResult(
            production_repo_path=str(self.resolve_path(production_repo_path)),
            target_file_path=str(target),
            target_component_name=component_name,
            language=language.value,
            suggested_features=suggested,
            tags=sorted(inventory.tags),
            interactive_tags=sorted(inventory.interactive_tags),
        )

    def load_design_html(self, design_repo_path: str, design_html_path: str) -> tuple[Path, str]:
        path = self.resolve_under_repo(design_repo_path, design_html_path)
        if path.suffix.lower() not in {".html", ".htm"}:
            raise RepoAccessError(
                "Design artifacts must be HTML files (.html or .htm).",
            )
        content = self.read_text_file(path)
        if detect_language(content) is not SourceLanguage.HTML:
            raise RepoAccessError(
                "Design artifact content must be HTML (doctype/html/head/body).",
                issues=[
                    ValidationIssue(
                        code="HTML_ONLY",
                        message="Only HTML design artifacts are supported in this workflow.",
                    )
                ],
            )
        return path, content

    def save_component(
        self,
        production_repo_path: str,
        target_file_path: str,
        source: str,
    ) -> tuple[Path, int]:
        if len(source.encode()) > self.settings.max_code_bytes:
            raise RepoAccessError(
                f"Source exceeds the {self.settings.max_code_bytes}-byte limit.",
            )
        target = self.resolve_under_repo(production_repo_path, target_file_path)
        if target.suffix.lower() not in {".jsx", ".tsx", ".js", ".ts"}:
            raise RepoAccessError(
                "Production component saves are limited to .jsx/.tsx/.js/.ts files.",
            )
        try:
            target.write_text(source, encoding="utf-8")
        except OSError as exc:
            raise RepoAccessError(f"File is not writable: {target}") from exc
        return target, len(source.encode())

    def _is_under_roots(self, path: Path) -> bool:
        for root in self.roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False


def _infer_component_name(source: str, path: Path) -> str:
    match = _COMPONENT_NAME.search(source)
    if match:
        return match.group(1)
    stem = re.sub(r"[^A-Za-z0-9_]", "", path.stem)
    if stem:
        return stem[0].upper() + stem[1:]
    return "DesignArtifact"


def _suggest_features(source: str, interactive_tags: set[str]) -> list[str]:
    features: list[str] = []
    button_labels = re.findall(
        r"<button\b[^>]*>(.*?)</button>",
        source,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for label in button_labels:
        cleaned = re.sub(r"<[^>]+>", "", label)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            features.append(f"{cleaned} action")
    for tag in sorted(interactive_tags):
        if tag == "button" and features:
            continue
        features.append(f"{tag} control")
    return list(dict.fromkeys(features))[:100]
