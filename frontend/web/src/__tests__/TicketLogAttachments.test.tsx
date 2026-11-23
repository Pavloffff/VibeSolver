import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClient } from '../shared/api/client'
import type { TicketLogAttachment } from '../shared/api/types'
import { I18nProvider } from '../shared/i18n'
import TicketLogAttachments from '../features/ticket-log-attachments'

const QUEUED: TicketLogAttachment = {
  id: 17,
  filename: 'incident.zip',
  size_bytes: 2048,
  status: 'queued',
  error: null,
  created_at: null,
  updated_at: null,
}

const READY: TicketLogAttachment = { ...QUEUED, status: 'ready' }
const FAILED: TicketLogAttachment = { ...QUEUED, status: 'failed', error: 'Некорректный архив' }

function renderPanel(api: Partial<ApiClient>, onUnreadyChange = vi.fn()) {
  render(
    <I18nProvider>
      <TicketLogAttachments ticketId={17} api={api as ApiClient} onUnreadyChange={onUnreadyChange} />
    </I18nProvider>,
  )
  return onUnreadyChange
}

beforeEach(() => {
  localStorage.setItem('vibesolver.lang', 'ru')
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('TicketLogAttachments', () => {
  it('uploads an archive, lists it and polls until processing completes', async () => {
    vi.useFakeTimers()
    const api = {
      listTicketLogAttachments: vi.fn()
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([QUEUED])
        .mockResolvedValueOnce([READY]),
      uploadTicketLogAttachment: vi.fn().mockResolvedValue(QUEUED),
    }
    renderPanel(api)
    await act(async () => { await Promise.resolve() })

    const file = new File(['PK\x03\x04log'], 'incident.zip', { type: 'application/zip' })
    fireEvent.change(screen.getByLabelText('Прикрепить архив логов'), { target: { files: [file] } })

    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(api.uploadTicketLogAttachment).toHaveBeenCalledWith(17, file)
    expect(screen.getByText('В очереди')).toBeInTheDocument()
    expect(screen.getByText('incident.zip')).toBeInTheDocument()

    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.getByText('Готово')).toBeInTheDocument()
  })

  it('retries failed attachments and deletes them', async () => {
    const api = {
      listTicketLogAttachments: vi.fn().mockResolvedValueOnce([FAILED]).mockResolvedValueOnce([QUEUED]).mockResolvedValueOnce([]),
      retryTicketLogAttachment: vi.fn().mockResolvedValue(QUEUED),
      deleteTicketLogAttachment: vi.fn().mockResolvedValue(undefined),
    }
    renderPanel(api)

    expect(await screen.findByText('Некорректный архив')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Повторить обработку' }))
    await waitFor(() => expect(api.retryTicketLogAttachment).toHaveBeenCalledWith(17, 17))
    expect(await screen.findByText('В очереди')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Удалить архив incident.zip' }))
    await waitFor(() => expect(api.deleteTicketLogAttachment).toHaveBeenCalledWith(17, 17))
    expect(await screen.findByText('Архивы логов ещё не прикреплены.')).toBeInTheDocument()
  })
})

describe('ticket log attachment API', () => {
  it('sends multipart uploads and uses ticket-scoped lifecycle routes', async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify([QUEUED]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(QUEUED), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(QUEUED), { status: 202 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const api = new ApiClient(() => 'http://vibesolver.test')
    const file = new File(['archive'], 'incident.zip', { type: 'application/zip' })

    await expect(api.listTicketLogAttachments(17)).resolves.toEqual([QUEUED])
    await expect(api.uploadTicketLogAttachment(17, file)).resolves.toEqual(QUEUED)
    await expect(api.retryTicketLogAttachment(17, 17)).resolves.toEqual(QUEUED)
    await expect(api.deleteTicketLogAttachment(17, 17)).resolves.toBeUndefined()

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      'http://vibesolver.test/api/v1/tickets/17/log-attachments',
      'http://vibesolver.test/api/v1/tickets/17/log-attachments',
      'http://vibesolver.test/api/v1/tickets/17/log-attachments/17/retry',
      'http://vibesolver.test/api/v1/tickets/17/log-attachments/17',
    ])
    const uploadInit = fetchMock.mock.calls[1]?.[1]
    expect(uploadInit?.method).toBe('POST')
    expect(uploadInit?.headers).toEqual({})
    expect(uploadInit?.body).toBeInstanceOf(FormData)
  })
})

it.each([
  ['en', 'Could not queue the archive.', /KiB$/],
  ['ru', 'Не удалось поставить архив в очередь.', /КиБ$/],
  ['zh', '无法将压缩包加入队列。', /KiB$/],
])('localizes the archive size and stored queue failure in %s', async (lang, error, unit) => {
  const api = {
    listTicketLogAttachments: vi.fn().mockResolvedValue([{
      ...QUEUED, status: 'failed', error: 'Не удалось поставить архив в очередь',
    }]),
  }
  localStorage.setItem('vibesolver.lang', lang)
  render(
    <I18nProvider>
      <TicketLogAttachments ticketId={17} api={api as unknown as ApiClient} onUnreadyChange={vi.fn()} />
    </I18nProvider>,
  )

  expect(await screen.findByText(error)).toBeVisible()
  expect(screen.getByText(unit)).toBeVisible()
})
