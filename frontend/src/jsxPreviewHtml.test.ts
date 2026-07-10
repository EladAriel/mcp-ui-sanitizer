import { describe, expect, it } from 'vitest'

import {
  designRegionPreviewHtml,
  extractDataComponentRegion,
  extractJsxMarkup,
  extractStyleBlocks,
  jsxMarkupToHtml,
  jsxToPreviewHtml,
} from './jsxPreviewHtml'

const SAMPLE = `export function CheckoutCard() {
  return (
    <section className="checkout-card">
      <h1>Order summary</h1>
      <label htmlFor="qty">Quantity</label>
      <input id="qty" type="number" defaultValue={1} />
      <button type="button">Checkout</button>
    </section>
  );
}
`

describe('jsxPreviewHtml', () => {
  it('extracts the returned markup', () => {
    const markup = extractJsxMarkup(SAMPLE)
    expect(markup).toContain('<section')
    expect(markup).toContain('Checkout')
    expect(markup).not.toContain('export function')
  })

  it('normalizes JSX attributes for HTML preview', () => {
    const html = jsxMarkupToHtml(extractJsxMarkup(SAMPLE))
    expect(html).toContain('class="checkout-card"')
    expect(html).toContain('for="qty"')
    expect(html).toContain('value="1"')
    expect(html).not.toContain('className=')
    expect(html).not.toContain('htmlFor=')
    expect(html).not.toContain('{1}')
  })

  it('wraps markup in a document', () => {
    const doc = jsxToPreviewHtml(SAMPLE)
    expect(doc).toContain('<!doctype html>')
    expect(doc).toContain('Order summary')
  })

  it('extracts design style blocks for preview parity', () => {
    const html = `<!doctype html><html><head><style>
      :root { --accent: #0f6b4c; }
      .checkout-card h1 { font-size: 1.85rem; }
    </style></head><body></body></html>`
    const css = extractStyleBlocks(html)
    expect(css).toContain('--accent')
    expect(css).toContain('.checkout-card h1')
  })

  it('injects design CSS into the JSX preview document', () => {
    const css = ':root { --accent: #0f6b4c; }\n.price { color: var(--accent); }'
    const doc = jsxToPreviewHtml(SAMPLE, css)
    expect(doc).toContain('--accent')
    expect(doc).toContain('.price { color: var(--accent); }')
    expect(doc).toContain('checkout-card')
  })

  it('extracts the data-component region for focused design preview', () => {
    const html = `<!doctype html><html><body>
      <header>Chrome</header>
      <!--
        TARGET COMPONENT REGION
        data-component="CheckoutCard" mentioned in comment should not win
      -->
      <section class="panel checkout-card" data-component="CheckoutCard">
        <h1>Order summary</h1>
        <p class="subtitle">Review your bag</p>
      </section>
      <footer>Footer</footer>
    </body></html>`
    const region = extractDataComponentRegion(html, 'CheckoutCard')
    expect(region).toContain('Order summary')
    expect(region).toContain('panel checkout-card')
    expect(region).not.toContain('Chrome')
    expect(region).not.toContain('TARGET COMPONENT REGION')
    const preview = designRegionPreviewHtml(html, 'CheckoutCard')
    expect(preview).toContain('Order summary')
    expect(preview).not.toContain('Chrome')
  })

  it('extracts CheckoutCard from the example design dump despite preceding comments', async () => {
    const fs = await import('node:fs/promises')
    const path = await import('node:path')
    const file = path.resolve(
      __dirname,
      '../../example/design-repo/checkout/checkout-prototype.html',
    )
    const html = await fs.readFile(file, 'utf8')
    const region = extractDataComponentRegion(html, 'CheckoutCard')
    expect(region).toBeTruthy()
    expect(region!).toContain('panel checkout-card')
    expect(region!).toContain('Order summary')
    expect(region!).not.toContain('Northline Goods')
  })
})
