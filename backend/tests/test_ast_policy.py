import pytest

from app.ast_policy import PolicyError, inventory_artifact, validate_sanitized_artifact
from app.schemas import ErrorCode

RAW = """import { useState } from "react";
export function Card() {
  const [busy, setBusy] = useState(false);
  const fake = { label: "Buy" };
  return <button className="rounded" onClick={() => setBusy(true)}>Buy</button>;
}"""


def test_inventory_parses_tsx() -> None:
    inventory = inventory_artifact(RAW)
    assert inventory.imports == {"react"}
    assert "button" in inventory.tags


def test_valid_stateless_output_passes() -> None:
    output = """import { useState } from "react";
export function Card() {
  return <button className="rounded">Buy</button>;
}"""
    validate_sanitized_artifact(RAW, output, "Card", [])


def test_inline_handler_fails_closed() -> None:
    output = """import { useState } from "react";
export function Card() {
  return <button className="rounded" onClick={() => alert("Buy")}>Buy</button>;
}"""
    with pytest.raises(PolicyError) as captured:
        validate_sanitized_artifact(RAW, output, "Card", ["buy action"])
    assert captured.value.code is ErrorCode.POLICY_VIOLATION
    assert any(issue.code == "EXECUTABLE_HANDLER" for issue in captured.value.issues)


def test_new_copy_is_rejected() -> None:
    output = """export function Card() {
  return <button className="rounded">Purchase now</button>;
}"""
    with pytest.raises(PolicyError) as captured:
        validate_sanitized_artifact(RAW, output, "Card", [])
    assert any(issue.code == "NEW_LITERAL" for issue in captured.value.issues)


def test_invalid_syntax_is_rejected() -> None:
    with pytest.raises(PolicyError) as captured:
        inventory_artifact("export function Broken( {")
    assert captured.value.code is ErrorCode.INVALID_SYNTAX
