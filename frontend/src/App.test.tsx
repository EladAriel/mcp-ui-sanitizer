import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App', () => {
  it('renders the repository workflow inputs', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { name: 'UI Design Sanitizer' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Production repo path')).toBeInTheDocument()
    expect(screen.getByLabelText('Design repo path')).toBeInTheDocument()
    expect(screen.getByLabelText('Selected production file')).toBeInTheDocument()
    expect(screen.getByLabelText('Selected design HTML')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Run repository workflow' }),
    ).toBeEnabled()
  })
})
