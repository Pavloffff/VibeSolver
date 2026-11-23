import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ApiClient } from '../shared/api/client'
import { I18nProvider } from '../shared/i18n'
import ObservationInput from '../features/ui-observation/ui/ObservationInput'

function renderPage(api: Partial<ApiClient>) {
  render(<I18nProvider><ObservationInput ticketId={5} api={api as ApiClient} /></I18nProvider>)
}

beforeEach(() => {
  localStorage.setItem('vibesolver.lang', 'ru')
})

it('uploads and removes an engineer UI observation', async () => {
  const observation = { role: 'button', name: 'Save', width: 80, height: 24, visible: true, enabled: true, checked: null, observed_at: '2026-01-01T00:00:00Z' }
  const api = {
    getUiObservation: vi.fn().mockResolvedValue({ observation: null }), setUiObservation: vi.fn().mockResolvedValue({ observation }), deleteUiObservation: vi.fn().mockResolvedValue(undefined),
  }
  renderPage(api)
  const json = JSON.stringify({ ...observation, checked: undefined })
  const file = new File([json], 'observation.json', { type: 'application/json' })
  Object.defineProperty(file, 'text', { value: vi.fn().mockResolvedValue(json) })
  fireEvent.change(await screen.findByLabelText('Наблюдение интерфейса'), { target: { files: [file] } })
  await waitFor(() => expect(api.setUiObservation).toHaveBeenCalledWith(5, observation))
  fireEvent.click(await screen.findByRole('button', { name: 'Удалить наблюдение' }))
  await waitFor(() => expect(api.deleteUiObservation).toHaveBeenCalledWith(5))
})

it('opens the bundled observer in the system browser from desktop', async () => {
  const openUiObserver = vi.fn().mockResolvedValue({ ok: true })
  vi.stubGlobal('vibesolver', { openUiObserver })
  const api = { getUiObservation: vi.fn().mockResolvedValue({ observation: null }) }
  renderPage(api)
  fireEvent.click(await screen.findByRole('button', { name: 'Открыть помощник наблюдения' }))
  await waitFor(() => expect(openUiObserver).toHaveBeenCalledExactlyOnceWith('ru'))
  vi.unstubAllGlobals()
})

it('passes the selected language to the web helper', async () => {
  localStorage.setItem('vibesolver.lang', 'zh')
  renderPage({ getUiObservation: vi.fn().mockResolvedValue({ observation: null }) })

  expect(await screen.findByRole('link', { name: '打开观察助手' })).toHaveAttribute('href', './ui-observer.html?lang=zh')
})

it.each([
  ['ru', 'Наблюдение интерфейса', 'Выбрать файл'],
  ['zh', '界面观察', '选择文件'],
])('uses the app language %s for the visible file picker', async (lang, inputName, buttonText) => {
  vi.spyOn(window.navigator, 'language', 'get').mockReturnValue('en-US')
  localStorage.setItem('vibesolver.lang', lang)
  try {
    renderPage({ getUiObservation: vi.fn().mockResolvedValue({ observation: null }) })

    const input = await screen.findByLabelText(inputName)
    expect(input).toHaveAttribute('type', 'file')
    expect(input).toBeEnabled()
    expect(screen.getByText(buttonText)).toBeVisible()
    expect(screen.queryByText('Choose File')).not.toBeInTheDocument()
  } finally {
    vi.restoreAllMocks()
  }
})
