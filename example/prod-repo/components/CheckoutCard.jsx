export function CheckoutCard() {
  return (
    <section className="panel checkout-card" data-component="CheckoutCard" data-feature="CheckoutCard">
      <h1>Order summary</h1>
      <p className="subtitle">
        Review your bag before paying. This card sits inside a larger page
        dump that also includes shipping, payment, and recommendations.
      </p>

      <div className="line-item">
        <div>
          <div className="name">Canvas tote — charcoal</div>
          <div className="meta">SKU TTE-CHAR-01 · warehouse mock inventory</div>
        </div>
        <div className="price">$48.00</div>
      </div>

      <div className="controls">
        <label>
          Quantity
          <input type="number" name="quantity" min={1} defaultValue={2} />
        </label>

        <div className="actions">
          <button type="button">Checkout</button>
        </div>
      </div>
    </section>
  );
}