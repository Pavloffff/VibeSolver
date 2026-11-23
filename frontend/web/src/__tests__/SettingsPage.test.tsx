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
  it('updates an existing connection error when the language changes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(<I18nProvider><SettingsPage /></I18nProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Проверить соединение' }))
    expect(await screen.findByText(/Проверьте адрес сервера/)).toBeVisible()
    fireEvent.click(screen.getByLabelText('English'))
    expect(screen.getByText(/Check the server address/)).toBeVisible()
  })
  it('switches to English immediately without reload', async () => {
    render(
      <I18nProvider>
        <SettingsPage />
      </I18nProvider>,
    )
    expect(screen.queryByRole('button', { name: 'Сохранить' })).not.toBeInTheDocument()
    expect(screen.getByText('Проверить соединение')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('English'))

    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
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

  it('toggles experimental features and applies them immediately', () => {
    const onExperimentalChange = vi.fn()
    render(
      <I18nProvider>
        <SettingsPage experimental={false} onExperimentalChange={onExperimentalChange} />
      </I18nProvider>,
    )

    const toggle = screen.getByLabelText('Показывать экспериментальные функции')
    expect(toggle).not.toBeChecked()

    fireEvent.click(toggle)

    expect(onExperimentalChange).toHaveBeenCalledWith(true)
    expect(localStorage.getItem('vibesolver.experimental')).toBe('true')
  })

  it('leaves a working connection in place until a valid remote address is finished', () => {
    localStorage.setItem('vibesolver.lang', 'en')
    const initial = { mode: 'local', serverUrl: window.location.origin }
    localStorage.setItem('vibesolver.settings', JSON.stringify(initial))
    render(<I18nProvider><SettingsPage /></I18nProvider>)
    fireEvent.click(screen.getByLabelText('Remote server'))
    const field = screen.getByLabelText('Server address')
    fireEvent.change(field, { target: { value: 'bad address' } })
    fireEvent.blur(field)
    expect(screen.getByRole('alert')).toBeVisible()
    expect(JSON.parse(localStorage.getItem('vibesolver.settings')!)).toEqual(initial)
    fireEvent.change(field, { target: { value: 'https://lab5.example/test/' } })
    fireEvent.keyDown(field, { key: 'Enter' })
    expect(JSON.parse(localStorage.getItem('vibesolver.settings')!)).toEqual({
      mode: 'remote', serverUrl: 'https://lab5.example/test',
    })
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
    fireEvent.blur(screen.getByLabelText('Server address'))

    await waitFor(() => {
      expect(saveConfig).toHaveBeenCalledTimes(1)
    })
    expect(saveConfig).toHaveBeenCalledWith({
      mode: 'remote',
      serverUrl: 'http://10.0.0.5:8000',
      lang: 'en',
    })
    expect(localStorage.getItem('vibesolver.settings')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
  })

  it('shows the bridge error when saving fails', async () => {
    const saveConfig = vi.fn().mockResolvedValue({ ok: false, error: 'boom' })
    vi.stubGlobal('vibesolver', { saveConfig })

    render(
      <I18nProvider>
        <SettingsPage />
      </I18nProvider>,
    )
    fireEvent.click(screen.getByLabelText('Remote server'))
    fireEvent.change(screen.getByLabelText('Server address'), { target: { value: 'https://lab5.example' } })
    fireEvent.blur(screen.getByLabelText('Server address'))

    expect(await screen.findByText('boom')).toBeInTheDocument()
    expect(screen.queryByText('Settings saved')).not.toBeInTheDocument()
    expect(localStorage.getItem('vibesolver.settings')).toBeNull()
  })

  it('persists desktop language immediately using the running window', async () => {
    const setLanguage = vi.fn().mockResolvedValue({ ok: true })
    const saveConfig = vi.fn()
    vi.stubGlobal('vibesolver', { setLanguage, saveConfig })
    render(<I18nProvider><SettingsPage /></I18nProvider>)
    fireEvent.click(screen.getByLabelText('中文'))
    expect(setLanguage).toHaveBeenCalledWith('zh')
    expect(saveConfig).not.toHaveBeenCalled()
    expect(document.documentElement.lang).toBe('zh')
  })
})
