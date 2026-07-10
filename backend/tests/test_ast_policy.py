import pytest

from app.ast_policy import PolicyError, inventory_artifact, validate_sanitized_artifact
from app.schemas import ErrorCode

RAW = """import { useState } from "react";
export function Card() {
  const [busy, setBusy] = useState(false);
  const fake = { label: "Buy" };
  return <button className="rounded" onClick={() => setBusy(true)}>Buy</button>;
}"""

RAW_HTML = """<!doctype html>
<html>
  <body>
    <section class="card">
      <h1>Order summary</h1>
      <button onclick="alert('pay')">Checkout</button>
      <input type="number" name="quantity" />
      <script>window.__x = 1</script>
    </section>
  </body>
</html>
"""


def test_inventory_parses_tsx() -> None:
    inventory = inventory_artifact(RAW)
    assert inventory.imports == {"react"}
    assert "button" in inventory.tags


def test_inventory_parses_html_tags_and_interactions() -> None:
    inventory = inventory_artifact(RAW_HTML)
    assert inventory.language.value == "html"
    assert "button" in inventory.tags
    assert "input" in inventory.tags
    assert "section" in inventory.tags
    assert inventory.interactive_tags >= {"button", "input"}


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


def test_allowlisted_callback_must_be_a_component_prop() -> None:
    output = """import { useState } from "react";
export function Card({ onBuy }: { onBuy: () => void }) {
  return <button className="rounded" onClick={onBuy}>Buy</button>;
}"""
    validate_sanitized_artifact(RAW, output, "Card", ["buy action"])


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


def test_html_onclick_fails_closed() -> None:
    dirty = """<!doctype html>
<html><body><button onclick="alert('pay')">Checkout</button></body></html>
"""
    with pytest.raises(PolicyError) as captured:
        validate_sanitized_artifact(RAW_HTML, dirty, "CheckoutCard", ["Checkout action"])
    assert any(issue.code == "EXECUTABLE_HANDLER" for issue in captured.value.issues)


def test_html_script_fails_closed() -> None:
    dirty = """<!doctype html>
<html><body><button>Checkout</button><script>window.__x=1</script></body></html>
"""
    with pytest.raises(PolicyError) as captured:
        validate_sanitized_artifact(RAW_HTML, dirty, "CheckoutCard", ["Checkout action"])
    assert any(issue.code == "FORBIDDEN_EMBEDDED_CODE" for issue in captured.value.issues)


def test_clean_html_passes() -> None:
    clean = """<!doctype html>
<html>
  <body>
    <section class="card">
      <h1>Order summary</h1>
      <button>Checkout</button>
      <input type="number" name="quantity" />
    </section>
  </body>
</html>
"""
    validate_sanitized_artifact(RAW_HTML, clean, "CheckoutCard", ["Checkout action"])


def test_merged_jsx_accepts_design_copy_within_prod_interactions() -> None:
    production = """export function CheckoutCard() {
  return (
    <section>
      <h1>Order summary</h1>
      <button type="button">Checkout</button>
    </section>
  );
}
"""
    sanitized = """<!doctype html>
<html><body>
  <section>
    <h1>Order summary</h1>
    <p>$99</p>
    <button>Checkout</button>
  </section>
</body></html>
"""
    merged = """export function CheckoutCard() {
  return (
    <section>
      <h1>Order summary</h1>
      <p>$99</p>
      <button type="button">Checkout</button>
    </section>
  );
}
"""
    from app.ast_policy import validate_merged_jsx

    validate_merged_jsx(production, sanitized, merged, "CheckoutCard", ["Checkout action"])


def test_merged_jsx_rejects_new_interactive_control() -> None:
    production = """export function CheckoutCard() {
  return <section><button type="button">Checkout</button></section>;
}
"""
    sanitized = """<!doctype html>
<html><body>
  <section>
    <button>Checkout</button>
    <input type="text" name="coupon" />
  </section>
</body></html>
"""
    merged = """export function CheckoutCard() {
  return (
    <section>
      <button type="button">Checkout</button>
      <input type="text" name="coupon" />
    </section>
  );
}
"""
    from app.ast_policy import validate_merged_jsx

    with pytest.raises(PolicyError) as captured:
        validate_merged_jsx(production, sanitized, merged, "CheckoutCard", ["Checkout action"])
    assert any(issue.code == "NEW_INTERACTION" for issue in captured.value.issues)


def test_extract_data_component_region_from_multi_feature_page() -> None:
    from app.ast_policy import extract_data_component_region, wrap_html_fragment

    html = """<!doctype html>
<html><body>
  <header>Chrome</header>
  <section class="panel checkout-card" data-component="CheckoutCard">
    <h1>Order summary</h1>
    <p class="subtitle">Review your bag</p>
  </section>
  <section data-feature="Other">Neighbor</section>
</body></html>
"""
    region = extract_data_component_region(html, "CheckoutCard")
    assert region is not None
    assert "panel checkout-card" in region
    assert "Order summary" in region
    assert "Chrome" not in region
    assert "Neighbor" not in region
    wrapped = wrap_html_fragment(region)
    assert "<!doctype html>" in wrapped
    assert "Order summary" in wrapped


def test_demote_form_wrappers_preserves_classes() -> None:
    from app.ast_policy import demote_form_wrappers

    html = (
        '<form class="controls" action="/mock" method="post">'
        "<label>Quantity<input type=\"number\" name=\"quantity\" /></label>"
        "</form>"
    )
    demoted = demote_form_wrappers(html)
    assert "<form" not in demoted.lower()
    assert demoted.startswith('<div class="controls">')
    assert demoted.endswith("</div>")
    assert "Quantity" in demoted

    jsx = (
        'export function CheckoutCard() {\n'
        '  return (\n'
        '    <form className="controls">\n'
        '      <div className="line-item"><div className="price">$48.00</div></div>\n'
        '    </form>\n'
        '  );\n'
        '}\n'
    )
    demoted_jsx = demote_form_wrappers(jsx)
    assert "<form" not in demoted_jsx.lower()
    assert 'className="controls"' in demoted_jsx
    assert 'className="line-item"' in demoted_jsx
