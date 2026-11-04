import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import App from '../app/App'
import { I18nProvider } from '../shared/i18n'

afterEach(() => {
  vi.unstubAllGlobals()
  delete document.documentElement.dataset.theme
})

beforeEach(() => {
  localStorage.setItem('vibesolver.theme', 'light')
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
    expect(screen.getByRole('button', { name: 'Projects' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
  })

  it('toggles between light and dark themes and remembers the selection', async () => {
    vi.stubGlobal('vibesolver', {})
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => '[]' }))
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    )

    await screen.findByText('Start with your first project')
    fireEvent.click(screen.getByRole('button', { name: 'Dark theme' }))

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('vibesolver.theme')).toBe('dark')
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
