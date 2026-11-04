import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../App'
import { I18nProvider } from '../i18n'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App mode screen', () => {
  it('skips the mode screen when the electron bridge is present', () => {
    vi.stubGlobal('vibesolver', {})
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    )
    expect(screen.queryByText('Choose the working mode')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sources' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
  })

  it('shows the mode screen in the browser', () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    )
    expect(screen.getByText('Choose the working mode')).toBeInTheDocument()
  })
})
