import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum

import tree_sitter_html
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Tree

from app.schemas import ErrorCode, ValidationIssue


class SourceLanguage(StrEnum):
    TSX = "tsx"
    HTML = "html"


class PolicyError(Exception):
    def __init__(self, code: ErrorCode, message: str, issues: list[ValidationIssue]):
        super().__init__(message)
        self.code = code
        self.issues = issues


@dataclass(slots=True)
class ArtifactInventory:
    language: SourceLanguage
    imports: set[str] = field(default_factory=set)
    tags: set[str] = field(default_factory=set)
    text_literals: set[str] = field(default_factory=set)
    interactive_tags: set[str] = field(default_factory=set)


_TSX = Language(tree_sitter_typescript.language_tsx())
_HTML = Language(tree_sitter_html.language())
_HTML_START = re.compile(r"^\s*(?:<!doctype\s+html|<html|<head|<body)", re.IGNORECASE)
_IMPORT_SOURCE = re.compile(r"\bfrom\s+['\"]([^'\"]+)['\"]|^\s*import\s+['\"]([^'\"]+)['\"]")
_INTERACTIVE_TAGS = {"button", "input", "select", "textarea", "form", "a"}
_HTML_TAG_NODES = {"start_tag", "self_closing_tag"}
_JSX_TAG_NODES = {"jsx_opening_element", "jsx_self_closing_element"}
_HTML_EVENT_ATTR = re.compile(r"^on[a-z]+$", re.IGNORECASE)
_FORBIDDEN_HTML_ELEMENTS = {"script", "style"}
_FORM_OPEN = re.compile(r"<form\b([^>]*)>", re.IGNORECASE)
_FORM_CLOSE = re.compile(r"</form\s*>", re.IGNORECASE)
_FORBIDDEN_CALLS = {
    "useState",
    "useReducer",
    "useEffect",
    "useLayoutEffect",
    "useContext",
    "useSyncExternalStore",
    "fetch",
    "setTimeout",
    "setInterval",
    "requestAnimationFrame",
}
_FORBIDDEN_OBJECTS = {
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "axios",
    "router",
    "history",
    "location",
}


def detect_language(code: str) -> SourceLanguage:
    return SourceLanguage.HTML if _HTML_START.search(code) else SourceLanguage.TSX


def _parser(language: SourceLanguage) -> Parser:
    return Parser(_HTML if language is SourceLanguage.HTML else _TSX)


def _walk(node: Node) -> Iterator[Node]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _tag_name(node: Node, source: bytes) -> str | None:
    """Resolve a tag name from JSX (field `name`) or HTML (`tag_name` child)."""
    name = node.child_by_field_name("name")
    if name:
        return _text(name, source)
    for child in node.named_children:
        if child.type == "tag_name":
            return _text(child, source)
    return None


def _issue(code: str, message: str, node: Node | None = None) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        message=message,
        line=node.start_point.row + 1 if node else None,
        column=node.start_point.column + 1 if node else None,
    )


def parse_artifact(code: str, language: SourceLanguage | None = None) -> tuple[Tree, bytes]:
    selected = language or detect_language(code)
    source = code.encode()
    tree = _parser(selected).parse(source)
    if tree.root_node.has_error:
        error_node = next(
            (node for node in _walk(tree.root_node) if node.is_error or node.is_missing),
            tree.root_node,
        )
        raise PolicyError(
            ErrorCode.INVALID_SYNTAX,
            "Artifact is not valid HTML/JSX/TSX.",
            [
                _issue(
                    "SYNTAX_ERROR", "Parser could not produce a complete syntax tree.", error_node
                )
            ],
        )
    return tree, source


def _html_attr_value(start_tag: Node, source: bytes, attr_name: str) -> str | None:
    for child in start_tag.named_children:
        if child.type != "attribute":
            continue
        name_node = next(
            (part for part in child.named_children if part.type == "attribute_name"),
            None,
        )
        if not name_node or _text(name_node, source) != attr_name:
            continue
        value_node = next(
            (part for part in child.named_children if part.type == "quoted_attribute_value"),
            None,
        )
        if not value_node:
            return ""
        raw = _text(value_node, source).strip()
        if len(raw) >= 2 and raw[0] in {'"', "'"} and raw[-1] == raw[0]:
            return raw[1:-1]
        return raw
    return None


def extract_data_component_region(html: str, component_name: str) -> str | None:
    """Return outer HTML for the first element with matching data-component, if any."""
    target = component_name.strip()
    if not target:
        return None
    tree, source = parse_artifact(html, SourceLanguage.HTML)
    for node in _walk(tree.root_node):
        if node.type != "element":
            continue
        start = next((child for child in node.children if child.type == "start_tag"), None)
        if not start:
            continue
        if _html_attr_value(start, source, "data-component") == target:
            return _text(node, source)
    return None


def wrap_html_fragment(fragment: str) -> str:
    """Wrap a markup fragment in a minimal HTML document for sanitizer input."""
    body = fragment.strip()
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head><meta charset=\"utf-8\" /></head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def demote_form_wrappers(code: str) -> str:
    """Replace <form> wrappers with <div> so layout survives without new interactions.

    After handlers are stripped, form is only a presentation wrapper. Keeping it as
    <form> fails merge policy when production JSX has no form tag; LLM repair then
    often corrupts structure (e.g. div.line-item → invalid p.line-item).
    """

    def _open(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        # Drop form-only attributes that are meaningless on a div.
        attrs = re.sub(
            r"\s(action|method|enctype|novalidate|target)\s*=\s*(['\"][^'\"]*['\"]|[^\s>]+)",
            "",
            attrs,
            flags=re.IGNORECASE,
        )
        return f"<div{attrs}>"

    return _FORM_CLOSE.sub("</div>", _FORM_OPEN.sub(_open, code))


def inventory_artifact(code: str, language: SourceLanguage | None = None) -> ArtifactInventory:
    selected = language or detect_language(code)
    tree, source = parse_artifact(code, selected)
    inventory = ArtifactInventory(language=selected)

    for node in _walk(tree.root_node):
        node_text = _text(node, source)
        if node.type == "import_statement":
            match = _IMPORT_SOURCE.search(node_text)
            if match:
                inventory.imports.add(match.group(1) or match.group(2))
        elif node.type in _JSX_TAG_NODES | _HTML_TAG_NODES:
            tag = _tag_name(node, source)
            if tag:
                inventory.tags.add(tag)
                if tag.lower() in _INTERACTIVE_TAGS:
                    inventory.interactive_tags.add(tag.lower())
        elif node.type in {"string", "jsx_text", "text", "attribute_value"}:
            # HTML attrs use attribute_value; JSX uses string — include both for merge policy.
            normalized = re.sub(r"\s+", " ", node_text.strip().strip("'\"`"))
            if normalized:
                inventory.text_literals.add(normalized)
    return inventory


def _callee_name(node: Node, source: bytes) -> str:
    function = node.child_by_field_name("function")
    return _text(function, source).strip() if function else ""


def _validate_stateless(
    tree: Tree, source: bytes, allowed_features: list[str]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    allow_callbacks = bool(allowed_features)
    component_parameters = " ".join(
        _text(node, source) for node in _walk(tree.root_node) if node.type == "formal_parameters"
    )

    for node in _walk(tree.root_node):
        node_text = _text(node, source)
        if node.type == "call_expression":
            callee = _callee_name(node, source)
            leaf = callee.rsplit(".", 1)[-1]
            if leaf in _FORBIDDEN_CALLS or callee.split(".", 1)[0] in _FORBIDDEN_OBJECTS:
                issues.append(
                    _issue("FORBIDDEN_CALL", f"Behavioral call '{callee}' is not allowed.", node)
                )
        elif node.type == "member_expression":
            root = node_text.split(".", 1)[0]
            if root in _FORBIDDEN_OBJECTS:
                issues.append(
                    _issue("FORBIDDEN_RUNTIME_API", f"Runtime API '{root}' is not allowed.", node)
                )
        elif node.type == "variable_declarator":
            value = node.child_by_field_name("value")
            if value and value.type in {"array", "object"}:
                issues.append(
                    _issue(
                        "LOCAL_MOCK_DATA",
                        "Local array/object data must be supplied through component props.",
                        node,
                    )
                )
        elif node.type == "jsx_attribute":
            name = node.child_by_field_name("name")
            if not name and node.named_children:
                name = node.named_children[0]
            if not name:
                continue
            attribute = _text(name, source)
            if not re.fullmatch(r"on[A-Z].*", attribute):
                continue
            value = node.child_by_field_name("value")
            if not value and len(node.named_children) > 1:
                value = node.named_children[1]
            value_text = _text(value, source) if value else ""
            reference = re.fullmatch(
                r"\{\s*([A-Za-z_$][\w$]*)(?:\.[A-Za-z_$][\w$]*)?\s*\}",
                value_text,
            )
            is_callback_reference = bool(
                reference
                and re.search(
                    rf"\b{re.escape(reference.group(1))}\b",
                    component_parameters,
                )
            )
            if not allow_callbacks or not is_callback_reference:
                issues.append(
                    _issue(
                        "EXECUTABLE_HANDLER",
                        f"'{attribute}' must be removed or reference an allowed callback prop.",
                        node,
                    )
                )
        elif node.type == "attribute":
            attr_name = next(
                (child for child in node.named_children if child.type == "attribute_name"),
                None,
            )
            if not attr_name:
                continue
            attribute = _text(attr_name, source)
            if _HTML_EVENT_ATTR.fullmatch(attribute):
                issues.append(
                    _issue(
                        "EXECUTABLE_HANDLER",
                        f"HTML event handler '{attribute}' must be removed.",
                        node,
                    )
                )
        elif node.type in {"script_element", "style_element"}:
            issues.append(
                _issue(
                    "FORBIDDEN_EMBEDDED_CODE",
                    f"Embedded <{node.type.removesuffix('_element')}> is not allowed.",
                    node,
                )
            )
        elif node.type in _HTML_TAG_NODES:
            tag = _tag_name(node, source)
            if tag and tag.lower() in _FORBIDDEN_HTML_ELEMENTS:
                issues.append(
                    _issue(
                        "FORBIDDEN_EMBEDDED_CODE",
                        f"Embedded <{tag.lower()}> is not allowed.",
                        node,
                    )
                )
    return issues


def validate_sanitized_artifact(
    raw_code: str,
    sanitized_code: str,
    target_component_name: str,
    allowed_features: list[str],
) -> None:
    before = inventory_artifact(raw_code)
    tree, source = parse_artifact(sanitized_code, before.language)
    after = inventory_artifact(sanitized_code, before.language)
    issues = _validate_stateless(tree, source, allowed_features)

    if before.language is SourceLanguage.TSX and target_component_name not in sanitized_code:
        issues.append(
            _issue(
                "MISSING_TARGET_COMPONENT",
                f"Output no longer defines or references '{target_component_name}'.",
            )
        )

    for source_import in sorted(after.imports - before.imports):
        issues.append(_issue("NEW_IMPORT", f"Output introduced dependency '{source_import}'."))

    for tag in sorted(after.tags - before.tags):
        issues.append(_issue("NEW_ELEMENT", f"Output introduced element '{tag}'."))

    for literal in sorted(after.text_literals - before.text_literals):
        issues.append(_issue("NEW_LITERAL", f"Output introduced text or a value: {literal!r}."))

    for tag in sorted(after.interactive_tags - before.interactive_tags):
        issues.append(_issue("NEW_INTERACTION", f"Output introduced interactive element '{tag}'."))

    if issues:
        raise PolicyError(
            ErrorCode.POLICY_VIOLATION,
            "Sanitized output failed the stateless component policy.",
            issues,
        )


def validate_merged_jsx(
    production_jsx: str,
    sanitized_html: str,
    merged_jsx: str,
    target_component_name: str,
    allowed_features: list[str],
) -> None:
    """Fail-closed checks for HTML presentation merged into a production JSX component."""
    production = inventory_artifact(production_jsx, SourceLanguage.TSX)
    design = inventory_artifact(sanitized_html, SourceLanguage.HTML)
    tree, source = parse_artifact(merged_jsx, SourceLanguage.TSX)
    after = inventory_artifact(merged_jsx, SourceLanguage.TSX)
    issues = _validate_stateless(tree, source, allowed_features)

    if target_component_name not in merged_jsx:
        issues.append(
            _issue(
                "MISSING_TARGET_COMPONENT",
                f"Output no longer defines or references '{target_component_name}'.",
            )
        )

    allowed_imports = production.imports
    for source_import in sorted(after.imports - allowed_imports):
        issues.append(_issue("NEW_IMPORT", f"Output introduced dependency '{source_import}'."))

    allowed_tags = {tag.lower() for tag in production.tags | design.tags}
    for tag in sorted(after.tags):
        if tag.lower() not in allowed_tags:
            issues.append(_issue("NEW_ELEMENT", f"Output introduced element '{tag}'."))

    allowed_literals = production.text_literals | design.text_literals
    for literal in sorted(after.text_literals - allowed_literals):
        issues.append(_issue("NEW_LITERAL", f"Output introduced text or a value: {literal!r}."))

    allowed_interactions = production.interactive_tags
    for tag in sorted(after.interactive_tags - allowed_interactions):
        issues.append(
            _issue("NEW_INTERACTION", f"Output introduced interactive element '{tag}'.")
        )

    if issues:
        raise PolicyError(
            ErrorCode.POLICY_VIOLATION,
            "Merged JSX failed the production presentation policy.",
            issues,
        )
