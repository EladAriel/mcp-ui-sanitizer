# Example mock repositories

Local fixtures for manually testing the HTML repository workflow UI.

## Layout

```text
example/
  prod-repo/
    components/CheckoutCard.jsx    # lean production React target
  design-repo/
    checkout/checkout-prototype.html   # multi-feature HTML page dump
    checkout/CheckoutCard.jsx          # parallel JSX (not selectable yet)
    notes.txt                          # filtered out of design browse
```

## What the design HTML represents

Real design handoffs are often **one HTML page with many features**, not a
single-component file. `checkout-prototype.html` is built that way on purpose:

| Region (`data-feature`) | Role |
| --- | --- |
| Site header / nav | Site chrome — not CheckoutCard |
| Product recommendations | Separate merchandising feature |
| Shipping address form | Separate checkout step |
| **`data-component="CheckoutCard"`** | **The region that maps to production** |
| Payment methods | Separate payment feature |
| Order tracking teaser | Account / post-purchase UI |
| Footer | Site chrome |

Inside the CheckoutCard region, the dump still overshoots production with
coupon / save-for-later / size / gift note / help, plus `onclick` and `<script>`.

**How to extract the right design for your component**

1. Select the production target (`CheckoutCard.jsx`) so inventory suggests only
   what that component supports (`Checkout action`, `input control`).
2. Point the workflow at the whole multi-feature HTML dump.
3. Keep that allowlist — the sanitizer must drop neighboring panels and
   design-only controls, then merge presentation into the production JSX.
4. Compare design HTML vs JSX previews and the before/after JSX diff; save when
   the extracted card looks right.

## Configure workspace roots

The API only reads paths under `SANITIZER_WORKSPACE_ROOTS`. Point it at this
`example` directory (or the repo root), then restart the backend:

```bash
# In backend/.env — use your absolute path
SANITIZER_WORKSPACE_ROOTS=/home/you/eladDevelop/mcp-ui-sanitizer/example
```

## Paths to paste in the UI

Replace `/home/you/.../example` with your absolute path to this folder.

| Field | Value |
| --- | --- |
| Production repo | `…/example/prod-repo` |
| Design repo | `…/example/design-repo` |
| Target file (after browse) | `components/CheckoutCard.jsx` |
| Design HTML (after browse) | `checkout/checkout-prototype.html` |

## Intentional feature gap

**Production** (`CheckoutCard.jsx`) only has:

- Checkout button → suggested `Checkout action`
- Quantity `input` → suggested `input control`

**Design dump** also includes neighboring features (recommendations, shipping,
payment, tracking, nav/footer) and, inside the card: Apply coupon / Save for
later, size `select`, gift-note `textarea`, help `a`, wrapping `form`, promo
banner, fake price/status, `onclick` handlers, and inline `<script>`.

Leave the inventory-suggested allowlist as-is when you run the workflow so the
sanitizer must extract CheckoutCard presentation only.

## Design browse note

Design browse uses `html_only`, so design-repo `CheckoutCard.jsx` and `notes.txt`
stay on disk for inspection but do not appear in the design file list. Select
`checkout/checkout-prototype.html` as the design artifact. Production browse
lists `.jsx` normally — select `components/CheckoutCard.jsx`.

## Manual checklist

1. Set `SANITIZER_WORKSPACE_ROOTS` and restart the backend.
2. Paste the production and design repo paths above.
3. Browse production → select `components/CheckoutCard.jsx` → confirm suggested features are roughly `Checkout action`, `input control`.
4. Browse design → confirm only `.html` files appear → select `checkout/checkout-prototype.html`.
5. Open the HTML preview and note multiple feature panels; only the block tagged
   `Target · CheckoutCard` is the production surface.
6. Run the workflow → watch the execution trace → compare:
   - design HTML preview vs production JSX (after) preview
   - production JSX before vs after text diff
7. Optionally click **Save to production** to write the after-JSX over the selected file.
8. Keep inventory-suggested allowlist unchanged so neighboring features and
   design-only controls are dropped.
