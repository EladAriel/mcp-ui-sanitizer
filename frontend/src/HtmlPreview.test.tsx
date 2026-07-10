import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import HtmlPreview from './HtmlPreview'

describe('HtmlPreview', () => {
  it('renders sandboxed before/after iframes without script privileges', () => {
    render(
      <HtmlPreview
        title="Before (design HTML)"
        html={'<!doctype html><html><body><button onclick="alert(1)">Go</button></body></html>'}
      />,
    )

    const frame = screen.getByTitle('Before (design HTML)') as HTMLIFrameElement
    expect(frame.tagName).toBe('IFRAME')
    expect(frame.getAttribute('sandbox')).toBe('')
    expect(frame.getAttribute('referrerpolicy') ?? frame.referrerPolicy).toBe('no-referrer')
    expect(frame.srcdoc).toContain('Go')
  })
})
