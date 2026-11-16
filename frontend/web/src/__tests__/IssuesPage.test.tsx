import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ApiClient } from '../shared/api/client'
import type { TicketBrief, TicketDetail } from '../shared/api/types'
import IssuesPage from '../pages/issues-page'
import { I18nProvider } from '../shared/i18n'

const TICKET: TicketBrief = { id: 5, title: 'Не работает вход', status: 'new', created_at: null }
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
    { step: 'triage', input_data: {}, output_data: { category: 'auth' }, model_id: 1, duration_ms: 40, created_at: null },
  ],
}

function renderPage(api: Partial<ApiClient>) {
  render(
    <I18nProvider>
      <IssuesPage projectId={1} projectName="demo" api={api as ApiClient} />
    </I18nProvider>,
  )
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
      getTicket: vi.fn().mockResolvedValue(DETAIL),
      runTicket: vi.fn().mockResolvedValue(DETAIL),
    }
    renderPage(api)

    expect(await screen.findByText('Не работает вход')).toBeInTheDocument()
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
      createTicket: vi.fn().mockResolvedValue(TICKET),
      getTicket: vi.fn().mockResolvedValue(DETAIL),
    }
    renderPage(api)

    fireEvent.change(await screen.findByLabelText('Заголовок'), { target: { value: 'Не работает вход' } })
    fireEvent.change(screen.getByLabelText('Описание'), { target: { value: 'При входе возвращается 401' } })
    fireEvent.click(screen.getByRole('button', { name: /Добавить обращение/ }))

    await waitFor(() => expect(api.createTicket).toHaveBeenCalledWith(1, 'Не работает вход', 'При входе возвращается 401'))
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
      getTicket: vi.fn().mockResolvedValue(escalated),
    }
    renderPage(api)

    fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
    expect(await screen.findByText('Эскалировано инженеру')).toBeInTheDocument()
    expect(screen.getByText('В индексах нет данных о этой версии.')).toBeInTheDocument()
  })
})
