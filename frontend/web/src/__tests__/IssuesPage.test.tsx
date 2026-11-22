import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ApiClient } from '../shared/api/client'
import type { TicketBrief, TicketDetail } from '../shared/api/types'
import type { TicketLogAttachment } from '../shared/api/types'
import IssuesPage from '../pages/issues-page'
import { I18nProvider } from '../shared/i18n'

const TICKET: TicketBrief = { id: 5, title: 'Не работает вход', status: 'new', created_at: null }
const QUEUED_LOG: TicketLogAttachment = {
  id: 17,
  filename: 'incident.zip',
  size_bytes: 2048,
  status: 'queued',
  error: null,
  created_at: null,
  updated_at: null,
}
const DETAIL: TicketDetail = {
  ticket: {
    id: 5,
    source_id: 1,
    title: 'Не работает вход',
    description: 'При входе возвращается 401',
    status: 'answered',
    triage: { category: 'auth', severity: 'high', summary: 'Пользователь не входит' },
    answer: 'Сбросьте пароль через форму восстановления.',
    escalate_reason: null,
    citations: [
      { source_ref: 'run:1:a.py:10', path: 'a.py', index_type: 'code', start_line: 10, end_line: 20 },
    ],
    created_at: null,
    updated_at: null,
  },
  steps: [
    { step: 'triage', input_data: {}, output_data: { category: 'auth' }, model_id: 1, duration_ms: 40, tokens_in: null, tokens_out: null, cost_usd: null, created_at: null },
  ],
}

function renderPage(api: Partial<ApiClient>) {
  render(
    <I18nProvider>
      <IssuesPage projectId={1} projectName="demo" api={api as ApiClient} />
    </I18nProvider>,
  )
}

function textFile(name: string, contents: string, read = vi.fn().mockResolvedValue(contents)) {
  const file = new File([contents], name, { type: 'text/plain' })
  Object.defineProperty(file, 'text', { configurable: true, value: read })
  return { file, read }
}

beforeEach(() => {
  localStorage.setItem('vibesolver.lang', 'ru')
})

describe('IssuesPage', () => {
  it('shows existing tickets and runs the pipeline', async () => {
    const api = {
      listTickets: vi.fn().mockResolvedValue([TICKET]),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null, ticket_resolution: null }),
      getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
      getTicket: vi.fn().mockResolvedValue(DETAIL),
      listTicketLogAttachments: vi.fn().mockResolvedValue([]),
      runTicket: vi.fn().mockResolvedValue(DETAIL),
    }
    renderPage(api)

    expect(await screen.findByText('Не работает вход')).toBeInTheDocument()
    expect(await screen.findByLabelText('Модель триажа')).toBeInTheDocument()
    expect(screen.getByLabelText('Модель решения')).toBeInTheDocument()
    expect(screen.getByLabelText('Недорогая модель для простых обращений')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Статистика обращений' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Запустить агентов' }))

    await waitFor(() => expect(api.runTicket).toHaveBeenCalledWith(5))
    expect(await screen.findByText('Ответ')).toBeInTheDocument()
    expect(screen.getByText('Сбросьте пароль через форму восстановления.')).toBeInTheDocument()
    expect(screen.getByText('a.py')).toBeInTheDocument()
    expect(screen.getByText('Трассировка агентов')).toBeInTheDocument()
  })

  it('creates a ticket from the form', async () => {
    const api = {
      listTickets: vi.fn().mockResolvedValue([]),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
      createTicket: vi.fn().mockResolvedValue(TICKET),
      getTicket: vi.fn().mockResolvedValue(DETAIL),
    }
    renderPage(api)

    fireEvent.change(await screen.findByLabelText('Заголовок'), { target: { value: 'Не работает вход' } })
    fireEvent.change(screen.getByLabelText('Описание'), { target: { value: 'При входе возвращается 401' } })
    fireEvent.click(screen.getByRole('button', { name: /Добавить обращение/ }))

    await waitFor(() => expect(api.createTicket).toHaveBeenCalledWith(1, 'Не работает вход', 'При входе возвращается 401'))
  })

  it('disables running a selected issue while its log archive is processing', async () => {
    const newDetail: TicketDetail = {
      ...DETAIL,
      ticket: { ...DETAIL.ticket, status: 'new', answer: null, citations: [] },
    }
    const api = {
      listTickets: vi.fn().mockResolvedValue([TICKET]),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
      getTicket: vi.fn().mockResolvedValue(newDetail),
      listTicketLogAttachments: vi.fn().mockResolvedValue([QUEUED_LOG]),
      runTicket: vi.fn(),
    }
    renderPage(api)

    fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
    expect(await screen.findByText('В очереди')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Запустить агентов' })).toBeDisabled()
    expect(api.runTicket).not.toHaveBeenCalled()
  })

  it('disables running pending-log tickets before opening their details', async () => {
    const pendingTicket = { ...TICKET, has_unready_log_attachments: true }
    const api = {
      listTickets: vi.fn().mockResolvedValue([pendingTicket]),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null, ticket_resolution: null }),
      getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
      getTicket: vi.fn().mockResolvedValue(DETAIL),
      listTicketLogAttachments: vi.fn().mockResolvedValue([QUEUED_LOG]),
      runTicket: vi.fn(),
    }
    renderPage(api)

    expect(await screen.findByText('Не работает вход')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Запустить агентов' })).toBeDisabled()
    expect(api.runTicket).not.toHaveBeenCalled()
  })

  it('prefills editable fields from a txt file and submits edited values', async () => {
    const api = {
      listTickets: vi.fn().mockResolvedValue([]),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
      createTicket: vi.fn().mockResolvedValue(TICKET),
      getTicket: vi.fn().mockResolvedValue(DETAIL),
    }
    renderPage(api)

    const { file, read } = textFile('issue.txt', 'Ошибка входа\nПри входе возвращается 401')
    fireEvent.change(await screen.findByLabelText('Загрузить обращение из TXT'), { target: { files: [file] } })

    expect(await screen.findByLabelText('Заголовок')).toHaveValue('Ошибка входа')
    expect(screen.getByLabelText('Описание')).toHaveValue('При входе возвращается 401')
    expect(read).toHaveBeenCalledOnce()
    expect(api.createTicket).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Заголовок'), { target: { value: 'Ошибка входа после обновления' } })
    fireEvent.click(screen.getByRole('button', { name: /Добавить обращение/ }))

    await waitFor(() => expect(api.createTicket).toHaveBeenCalledWith(1, 'Ошибка входа после обновления', 'При входе возвращается 401'))
  })

  it('rejects non-txt files without reading or changing the form', async () => {
    renderPage({
      listTickets: vi.fn().mockResolvedValue([]),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
    })

    const titleInput = await screen.findByLabelText('Заголовок')
    const descriptionInput = screen.getByLabelText('Описание')
    fireEvent.change(titleInput, { target: { value: 'Существующий заголовок' } })
    fireEvent.change(descriptionInput, { target: { value: 'Текущее описание обращения' } })
    const { file, read } = textFile('issue.pdf', 'should not be read')
    fireEvent.change(screen.getByLabelText('Загрузить обращение из TXT'), { target: { files: [file] } })

    expect(await screen.findByText('Выберите файл с расширением .txt.')).toBeInTheDocument()
    expect(titleInput).toHaveValue('Существующий заголовок')
    expect(descriptionInput).toHaveValue('Текущее описание обращения')
    expect(read).not.toHaveBeenCalled()
  })

  it('rejects empty and incomplete text and reports file read errors', async () => {
    renderPage({
      listTickets: vi.fn().mockResolvedValue([]),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
    })

    const fileInput = await screen.findByLabelText('Загрузить обращение из TXT')
    const empty = textFile('empty.txt', '  \n\r\n')
    fireEvent.change(fileInput, { target: { files: [empty.file] } })
    expect(await screen.findByText('Файл должен содержать заголовок длиной 3–200 символов и описание длиной 10–20 000 символов.')).toBeInTheDocument()

    const incomplete = textFile('incomplete.txt', 'Вход не работает')
    fireEvent.change(fileInput, { target: { files: [incomplete.file] } })
    expect(await screen.findByText('Файл должен содержать заголовок длиной 3–200 символов и описание длиной 10–20 000 символов.')).toBeInTheDocument()

    const failed = textFile('unreadable.txt', '', vi.fn().mockRejectedValue(new Error('read failed')))
    fireEvent.change(fileInput, { target: { files: [failed.file] } })
    expect(await screen.findByText('Не удалось прочитать файл. Попробуйте выбрать его снова.')).toBeInTheDocument()
  })

  it('shows escalation result with reason', async () => {
    const escalated: TicketDetail = {
      ...DETAIL,
      ticket: {
        ...DETAIL.ticket,
        status: 'escalated',
        answer: null,
        escalate_reason: 'В индексах нет данных о этой версии.',
      },
    }
    const api = {
      listTickets: vi.fn().mockResolvedValue([{ ...TICKET, status: 'escalated' }]),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
      getTicket: vi.fn().mockResolvedValue(escalated),
    }
    renderPage(api)

    fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
    expect(await screen.findByText('Эскалировано инженеру')).toBeInTheDocument()
    expect(screen.getByText('В индексах нет данных о этой версии.')).toBeInTheDocument()
  })
})
