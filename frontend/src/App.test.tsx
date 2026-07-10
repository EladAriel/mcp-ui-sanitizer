import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App', () => {
  it('renders the sanitizer input workflow', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { name: 'UI Design Sanitizer' }),
    ).toBeInTheDocument()
    expect(
      (screen.getByLabelText('Raw prototype code') as HTMLTextAreaElement).value,
    ).toContain('CheckoutCard')
    expect(
      screen.getByRole('button', { name: 'Sanitize artifact' }),
    ).toBeEnabled()
  })
})
