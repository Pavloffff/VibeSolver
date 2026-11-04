import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import SettingsPage from '../pages/settings-page'
import { I18nProvider } from '../shared/i18n'

beforeEach(() => {
  localStorage.setItem('vibesolver.lang', 'ru')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SettingsPage language selector', () => {
  it('switches to English immediately without reload', async () => {
    render(
      <I18nProvider>
        <SettingsPage />
      </I18nProvider>,
    )
    expect(screen.getByText('Сохранить')).toBeInTheDocument()
    expect(screen.getByText('Проверить соединение')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('English'))

    expect(screen.getByText('Save')).toBeInTheDocument()
    expect(screen.getByText('Check connection')).toBeInTheDocument()
    expect(screen.getByText('Server address')).toBeInTheDocument()
    expect(localStorage.getItem('vibesolver.lang')).toBe('en')
  })

  it('persists a selected appearance theme', () => {
    const onThemeChange = vi.fn()
    render(
      <I18nProvider>
        <SettingsPage theme="light" onThemeChange={onThemeChange} />
      </I18nProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }))

    expect(onThemeChange).toHaveBeenCalledWith('dark')
    expect(localStorage.getItem('vibesolver.theme')).toBe('dark')
  })
})

describe('SettingsPage in electron mode', () => {
  beforeEach(() => {
    localStorage.setItem('vibesolver.lang', 'en')
  })

  it('saves through the bridge instead of localStorage', async () => {
    const saveConfig = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('vibesolver', { saveConfig })

    render(
      <I18nProvider>
        <SettingsPage />
      </I18nProvider>,
    )
    fireEvent.click(screen.getByLabelText('Remote server'))
    fireEvent.change(screen.getByLabelText('Server address'), {
      target: { value: 'http://10.0.0.5:8000' },
    })
    fireEvent.click(screen.getByText('Save'))

    await waitFor(() => {
      expect(saveConfig).toHaveBeenCalledTimes(1)
    })
    expect(saveConfig).toHaveBeenCalledWith({
      mode: 'remote',
      serverUrl: 'http://10.0.0.5:8000',
      lang: 'en',
    })
    expect(localStorage.getItem('vibesolver.settings')).toBeNull()
    expect(screen.getByText('Settings saved')).toBeInTheDocument()
  })

  it('shows the bridge error when saving fails', async () => {
    const saveConfig = vi.fn().mockResolvedValue({ ok: false, error: 'boom' })
    vi.stubGlobal('vibesolver', { saveConfig })

    render(
      <I18nProvider>
        <SettingsPage />
      </I18nProvider>,
    )
    fireEvent.click(screen.getByLabelText('Local'))
    fireEvent.click(screen.getByText('Save'))

    expect(await screen.findByText('boom')).toBeInTheDocument()
    expect(screen.queryByText('Settings saved')).not.toBeInTheDocument()
    expect(localStorage.getItem('vibesolver.settings')).toBeNull()
  })
})
