import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

const PROFILES = { profiles: [{ id: 1, name: 'Standard' }, { id: 2, name: 'Deep' }], nodes: [], edges: [] }

async function chooseProfile(id = '1') {
  fireEvent.change(await screen.findByLabelText('Профиль запуска'), { target: { value: id } })
}

function renderPage(api: Partial<ApiClient>, onOpenSolver?: () => void) {
  render(
    <I18nProvider>
      <IssuesPage projectId={1} projectName="demo" api={{ getSolverGraph: vi.fn().mockResolvedValue(PROFILES), ...api } as ApiClient} onOpenSolver={onOpenSolver} />
    </I18nProvider>,
  )
}

function openIntake() {
  const trigger = screen.getByRole('button', { name: 'Добавить обращение' })
  fireEvent.click(trigger)
  return { trigger, dialog: screen.getByRole('dialog', { name: 'Добавить обращение' }) }
}

function textFile(name: string, contents: string, read = vi.fn().mockResolvedValue(contents)) {
  const file = new File([contents], name, { type: 'text/plain' })
  Object.defineProperty(file, 'text', { configurable: true, value: read })
  return { file, read }
}

beforeEach(() => {
  localStorage.setItem('vibesolver.lang', 'ru')
  HTMLDialogElement.prototype.showModal ??= function () { this.open = true }
  HTMLDialogElement.prototype.close ??= function () { this.open = false }
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('IssuesPage', () => {
  it('opens a modal from the queue and preserves a draft across Escape and reopening', async () => {
    const api = {
      listTickets: vi.fn().mockResolvedValue([TICKET]),
      getTicketStats: vi.fn().mockResolvedValue(null),
      getTicket: vi.fn().mockResolvedValue(DETAIL),
      listTicketLogAttachments: vi.fn().mockResolvedValue([]),
      getTicketDiagnosticOptions: vi.fn().mockResolvedValue({ use_web_search: false }),
    }
    renderPage(api)
    fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Разрешить поиск в интернете' })).not.toBeInTheDocument()
    const { trigger, dialog } = openIntake()
    const title = within(dialog).getByLabelText('Заголовок')
    expect(title).toHaveFocus()
    fireEvent.change(title, { target: { value: 'Черновик обращения' } })
    const close = within(dialog).getByRole('button', { name: 'Закрыть форму' })
    const submit = within(dialog).getByRole('button', { name: 'Добавить обращение' })
    close.focus()
    fireEvent.keyDown(close, { key: 'Tab', shiftKey: true })
    expect(submit).toHaveFocus()
    fireEvent.keyDown(submit, { key: 'Tab' })
    expect(close).toHaveFocus()
    fireEvent(dialog, new Event('cancel', { cancelable: true }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    expect(within(openIntake().dialog).getByLabelText('Заголовок')).toHaveValue('Черновик обращения')
    expect(api.getTicketDiagnosticOptions).not.toHaveBeenCalled()
  })

  it('previews a ZIP as editable fields and retries log upload without creating a second ticket', async () => {
    const api = {
      listTickets: vi.fn().mockResolvedValue([TICKET]),
      getTicketStats: vi.fn().mockResolvedValue(null),
      previewTicketArchive: vi.fn().mockResolvedValue({ text: 'Ошибка входа\nПри входе возвращается 401' }),
      createTicket: vi.fn().mockResolvedValue(TICKET),
      getTicket: vi.fn().mockResolvedValue(DETAIL),
      listTicketLogAttachments: vi.fn().mockResolvedValue([]),
      uploadTicketLogAttachment: vi.fn().mockRejectedValueOnce(new Error('Upload failed')).mockResolvedValue(QUEUED_LOG),
    }
    renderPage(api)
    const { dialog } = openIntake()
    const archive = new File([], 'issue.zip', { type: 'application/zip' })
    const logs = new File([], 'logs.zip', { type: 'application/zip' })
    fireEvent.change(screen.getByLabelText('Способ создания'), { target: { value: 'zip' } })
    fireEvent.change(screen.getByLabelText('Загрузить обращение из ZIP'), { target: { files: [archive] } })
    expect(await screen.findByDisplayValue('Ошибка входа')).toBeVisible()
    expect(api.previewTicketArchive).toHaveBeenCalledWith(archive)
    expect(api.createTicket).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Заголовок'), { target: { value: 'Ошибка входа после обновления' } })
    fireEvent.change(screen.getByLabelText('Архивы журналов (необязательно)'), { target: { files: [logs] } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Добавить обращение' }))
    const close = within(dialog).getByRole('button', { name: 'Закрыть форму' })
    expect(close).toBeDisabled()
    fireEvent(dialog, new Event('cancel', { cancelable: true }))
    expect(dialog).toBeVisible()
    expect(await screen.findByRole('alert')).toHaveTextContent('Upload failed')
    fireEvent.click(close)
    const reopened = openIntake().dialog
    expect(within(reopened).getByText('logs.zip')).toBeVisible()
    fireEvent.click(within(reopened).getByRole('button', { name: 'Повторить загрузку журналов' }))
    await waitFor(() => expect(api.uploadTicketLogAttachment).toHaveBeenCalledTimes(2))
    expect(api.uploadTicketLogAttachment).toHaveBeenLastCalledWith(5, logs)
    expect(api.createTicket).toHaveBeenCalledExactlyOnceWith(1, 'Ошибка входа после обновления', 'При входе возвращается 401')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('passes an engineer comment on a repeat run', async () => {
    const api = {
      listTickets: vi.fn().mockResolvedValue([TICKET]),
      getTicketStats: vi.fn().mockResolvedValue(null),
      getTicket: vi.fn().mockResolvedValue(DETAIL),
      listTicketLogAttachments: vi.fn().mockResolvedValue([]),
      runTicket: vi.fn().mockResolvedValue(DETAIL),
    }
    renderPage(api)
    fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
    const evidence = await screen.findByRole('region', { name: 'Материалы для повторного запуска' })
    const comment = within(evidence).getByLabelText('Комментарий к повторному запуску')
    const archive = within(evidence).getByLabelText('Прикрепить архив логов')
    expect(comment.compareDocumentPosition(archive) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getAllByLabelText('Прикрепить архив логов')).toHaveLength(1)
    fireEvent.change(comment, { target: { value: '  Проверьте новый журнал  ' } })
    await chooseProfile()
    fireEvent.click(screen.getByRole('button', { name: 'Запустить снова' }))
    await waitFor(() => expect(api.runTicket).toHaveBeenCalledWith(5, 1, 'Проверьте новый журнал'))
  })

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
    expect(screen.queryByLabelText('Модель триажа')).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Статистика обращений' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Не работает вход/ }))
    await chooseProfile()
    fireEvent.click(await screen.findByRole('button', { name: 'Запустить снова' }))

    await waitFor(() => expect(api.runTicket).toHaveBeenCalledWith(5, 1))
    expect(await screen.findByRole('heading', { name: 'Предложение по решению' })).toBeInTheDocument()
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

    const { dialog } = openIntake()
    fireEvent.change(await screen.findByLabelText('Заголовок'), { target: { value: 'Не работает вход' } })
    fireEvent.change(screen.getByLabelText('Описание'), { target: { value: 'При входе возвращается 401' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Добавить обращение' }))

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
    await chooseProfile()
    expect(screen.getByRole('button', { name: 'Запустить агентов' })).toBeDisabled()
    expect(api.runTicket).not.toHaveBeenCalled()
  })

  it('disables running pending-log tickets after opening their details', async () => {
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

    fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
    await chooseProfile()
    expect(await screen.findByRole('button', { name: 'Запустить снова' })).toBeDisabled()
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

    const { dialog } = openIntake()
    fireEvent.change(screen.getByLabelText('Способ создания'), { target: { value: 'txt' } })
    const { file, read } = textFile('issue.txt', 'Ошибка входа\nПри входе возвращается 401')
    fireEvent.change(await screen.findByLabelText('Загрузить обращение из TXT'), { target: { files: [file] } })

    expect(await screen.findByLabelText('Заголовок')).toHaveValue('Ошибка входа')
    expect(screen.getByLabelText('Описание')).toHaveValue('При входе возвращается 401')
    expect(read).toHaveBeenCalledOnce()
    expect(api.createTicket).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Заголовок'), { target: { value: 'Ошибка входа после обновления' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Добавить обращение' }))

    await waitFor(() => expect(api.createTicket).toHaveBeenCalledWith(1, 'Ошибка входа после обновления', 'При входе возвращается 401'))
  })

  it('rejects non-txt files without reading or changing the form', async () => {
    renderPage({
      listTickets: vi.fn().mockResolvedValue([]),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
    })

    openIntake()
    const titleInput = await screen.findByLabelText('Заголовок')
    const descriptionInput = screen.getByLabelText('Описание')
    fireEvent.change(titleInput, { target: { value: 'Существующий заголовок' } })
    fireEvent.change(descriptionInput, { target: { value: 'Текущее описание обращения' } })
    fireEvent.change(screen.getByLabelText('Способ создания'), { target: { value: 'txt' } })
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

    openIntake()
    fireEvent.change(screen.getByLabelText('Способ создания'), { target: { value: 'txt' } })
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

it('shows a readable trace without raw JSON', async () => {
  const api = {
    listTickets: vi.fn().mockResolvedValue([TICKET]),
    listWorkspaceModels: vi.fn().mockResolvedValue([]),
    getProjectModelSelections: vi.fn().mockResolvedValue({}),
    getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
    getTicket: vi.fn().mockResolvedValue(DETAIL),
    listTicketLogAttachments: vi.fn().mockResolvedValue([]),
  }
  renderPage(api)
  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
  expect(await screen.findByText('Трассировка агентов')).toBeVisible()
  expect(screen.getByText('Входные данные')).toBeVisible()
  expect(document.querySelector('.issues-trace pre')).not.toBeInTheDocument()
})


it('blocks runs when project indexes are not ready', async () => {
  const api = {
    listTickets: vi.fn().mockResolvedValue([TICKET]),
    listWorkspaceModels: vi.fn().mockResolvedValue([]),
    getProjectModelSelections: vi.fn().mockResolvedValue({}),
    getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
    getProjectIndexStatus: vi.fn().mockResolvedValue({ ready: false, indexes: [] }),
    getTicket: vi.fn().mockResolvedValue(DETAIL),
    listTicketLogAttachments: vi.fn().mockResolvedValue([]),
  }
  renderPage(api)
  expect(await screen.findByText('Импортируйте проект и завершите все три индексации, чтобы открыть обращения.')).toBeInTheDocument()
  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
  await chooseProfile()
  expect(await screen.findByRole('button', { name: 'Запустить снова' })).toBeDisabled()
})

it('links to profile setup only when no profiles exist and leaves intake available', async () => {
  const onOpenSolver = vi.fn()
  renderPage({
    listTickets: vi.fn().mockResolvedValue([TICKET]),
    getTicketStats: vi.fn().mockResolvedValue(null),
    getSolverGraph: vi.fn().mockResolvedValue({ ...PROFILES, profiles: [] }),
    getTicket: vi.fn().mockResolvedValue(DETAIL),
    listTicketLogAttachments: vi.fn().mockResolvedValue([]),
  }, onOpenSolver)

  expect(screen.queryByRole('button', { name: 'Настроить профиль' })).not.toBeInTheDocument()
  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
  fireEvent.click(await screen.findByRole('button', { name: 'Настроить профиль' }))
  expect(onOpenSolver).toHaveBeenCalledOnce()
  expect(screen.getByRole('button', { name: 'Запустить снова' })).toBeDisabled()
  expect(screen.getByLabelText('Прикрепить архив логов')).toBeEnabled()
  expect(openIntake().dialog).toBeVisible()
})

it('sends the explicitly chosen profile on the first run', async () => {
  const api = {
    listTickets: vi.fn().mockResolvedValue([TICKET]),
    listWorkspaceModels: vi.fn().mockResolvedValue([]),
    getProjectModelSelections: vi.fn().mockResolvedValue({}),
    getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
    getSolverGraph: vi.fn().mockResolvedValue({ default_profile_id: 1, profiles: [{ id: 1, name: 'Standard' }, { id: 2, name: 'Deep' }], nodes: [], edges: [] }),
    getTicket: vi.fn().mockResolvedValue({ ...DETAIL, ticket: { ...DETAIL.ticket, status: 'new' } }),
    listTicketLogAttachments: vi.fn().mockResolvedValue([]),
    runTicket: vi.fn().mockResolvedValue(DETAIL),
  }
  renderPage(api)
  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
  fireEvent.change(await screen.findByLabelText('Профиль запуска'), { target: { value: '2' } })
  fireEvent.click(await screen.findByRole('button', { name: 'Запустить агентов' }))
  await waitFor(() => expect(api.runTicket).toHaveBeenCalledWith(5, 2))
})

it('asks for an explicit profile again after running and after changing tickets', async () => {
  const other = { ...TICKET, id: 6, title: 'Другой вопрос' }
  const api = {
    listTickets: vi.fn().mockResolvedValue([TICKET, other]),
    getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
    getSolverGraph: vi.fn().mockResolvedValue({ default_profile_id: 1, profiles: [{ id: 1, name: 'Standard' }, { id: 2, name: 'Deep' }], nodes: [], edges: [] }),
    getTicket: vi.fn().mockImplementation((id: number) => Promise.resolve({ ...DETAIL, ticket: { ...DETAIL.ticket, id, title: id === 5 ? TICKET.title : other.title } })),
    listTicketLogAttachments: vi.fn().mockResolvedValue([]),
    runTicket: vi.fn().mockResolvedValue(DETAIL),
  }
  renderPage(api)
  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
  const profile = await screen.findByLabelText('Профиль запуска')
  expect(profile).toHaveValue('')
  const rerun = screen.getByRole('button', { name: 'Запустить снова' })
  expect(rerun).toBeDisabled()
  fireEvent.click(rerun)
  expect(api.runTicket).not.toHaveBeenCalled()
  fireEvent.change(profile, { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Запустить снова' }))
  await waitFor(() => expect(api.runTicket).toHaveBeenCalledWith(5, 2))
  await waitFor(() => expect(profile).toHaveValue(''))
  fireEvent.change(profile, { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: /Другой вопрос/ }))
  await waitFor(() => expect(screen.getByLabelText('Профиль запуска')).toHaveValue(''))
})

it('summarizes evidence and refreshes the failed run detail', async () => {
  const failedDetail = { ...DETAIL, steps: [{ ...DETAIL.steps[0], step: 'investigate', output_data: { fragments: 3, refs: ['S1', 'S2'] }, tokens_in: 4, tokens_out: null }] }
  const api = {
    listTickets: vi.fn().mockResolvedValue([TICKET]),
    getTicketStats: vi.fn().mockResolvedValue({ total: 0, by_status: {}, completed: 0, autoresolve_rate: 0, tokens_in: 0, tokens_out: 0, cost_usd: null, avg_cost_usd: null, avg_tokens_per_ticket: 0 }),
    getTicket: vi.fn().mockResolvedValueOnce(DETAIL).mockResolvedValue(failedDetail),
    listTicketLogAttachments: vi.fn().mockResolvedValue([]),
    runTicket: vi.fn().mockRejectedValue(new Error('failed')),
  }
  renderPage(api)
  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
  await chooseProfile()
  fireEvent.click(await screen.findByRole('button', { name: 'Запустить снова' }))
  expect(await screen.findByText(/Фрагментов: 3/)).toBeInTheDocument()
  expect(screen.getByText(/4 \/ —/)).toBeInTheDocument()
  expect(api.getTicket).toHaveBeenCalledTimes(2)
})

it('copies the complete suggestion including long links and formatting', async () => {
  const answer = 'GET /api/reports\n\nhttps://example.com/' + 'reports/'.repeat(120)
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  renderPage({
    listTickets: vi.fn().mockResolvedValue([TICKET]),
    getTicketStats: vi.fn().mockResolvedValue(null),
    getTicket: vi.fn().mockResolvedValue({ ...DETAIL, ticket: { ...DETAIL.ticket, answer } }),
    listTicketLogAttachments: vi.fn().mockResolvedValue([]),
  })

  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
  fireEvent.click(await screen.findByRole('button', { name: 'Скопировать предложение' }))
  await waitFor(() => expect(writeText).toHaveBeenCalledWith(answer))
  expect(await screen.findByText('Предложение скопировано')).toBeVisible()
})

it('copies visible trace headings and fields in a readable format', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  renderPage({
    listTickets: vi.fn().mockResolvedValue([TICKET]),
    getTicketStats: vi.fn().mockResolvedValue(null),
    getTicket: vi.fn().mockResolvedValue(DETAIL),
    listTicketLogAttachments: vi.fn().mockResolvedValue([]),
  })

  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
  fireEvent.click(await screen.findByRole('button', { name: 'Скопировать трассировку' }))
  await waitFor(() => expect(writeText).toHaveBeenCalledOnce())
  const copied = writeText.mock.calls[0]?.[0]
  expect(copied).toMatch(/^История запусков\n/)
  expect(copied).toMatch(/Результат\nКатегория\nauth/)
  expect(await screen.findByText('Трассировка скопирована')).toBeVisible()
})

it('localizes displayed and copied trace metadata while preserving raw agent text', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  renderPage({
    listTickets: vi.fn().mockResolvedValue([TICKET]),
    getTicketStats: vi.fn().mockResolvedValue(null),
    getTicket: vi.fn().mockResolvedValue({
      ...DETAIL,
      steps: [{
        ...DETAIL.steps[0], status: 'completed',
        output_data: {
          severity: 'high',
          search_queries: ['find parser'],
          evidence: { S1: { source_ref: 'run:1:a.py:10', ticket_id: 5, attachment_id: null, event_timestamp: null } },
          routing: { tier: 'strong', reason: 'no low-cost model is configured; using the strong model' },
        },
      }],
    }),
    listTicketLogAttachments: vi.fn().mockResolvedValue([]),
  })

  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
  const trace = await screen.findByRole('region', { name: 'Трассировка агентов' })
  expect(within(trace).getByText('Высокая')).toBeVisible()
  expect(screen.getByText('Исходный код')).toBeVisible()
  expect(screen.getByText('Поисковые запросы')).toBeVisible()
  expect(screen.getByText('find parser')).toBeVisible()
  expect(within(trace).getByText('Ссылка на источник')).toBeVisible()
  expect(within(trace).getByText('Основная модель')).toBeVisible()
  expect(within(trace).getByText('В профиле не настроена бюджетная модель. Используется основная модель.')).toBeVisible()
  fireEvent.click(within(trace).getByRole('button', { name: 'Скопировать трассировку' }))
  await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining('Ссылка на источник')))
  expect(writeText.mock.calls[0]?.[0]).toContain('run:1:a.py:10')
})

it('summarizes recorded usage across runs and historical steps before the trace', async () => {
  const template = DETAIL.steps[0]!
  const run = {
    id: 41, profile_id: 1, profile_name: 'Standard', enabled: { triage: true, resolve: true },
    models: { ticket_resolution: null, ticket_triage: null, ticket_resolution_cheap: null },
    status: 'answered', created_at: '2026-01-01T00:00:00Z', finished_at: '2026-01-01T00:02:00Z', error: null,
  }
  const detail: TicketDetail = {
    ...DETAIL,
    runs: [run, { ...run, id: 42 }],
    steps: [
      { ...template, run_id: 41, duration_ms: 10, tokens_in: 100, tokens_out: 20, cost_usd: 0.001 },
      { ...template, run_id: 42, duration_ms: 20, tokens_in: 22, tokens_out: null, cost_usd: null },
      { ...template, run_id: null, duration_ms: 30, tokens_in: 0, tokens_out: 1, cost_usd: 0 },
      { ...template, run_id: 42, model_id: null, duration_ms: 2, tokens_in: null, tokens_out: null, cost_usd: null },
    ],
  }
  renderPage({
    listTickets: vi.fn().mockResolvedValue([TICKET]), getTicketStats: vi.fn().mockResolvedValue(null),
    getTicket: vi.fn().mockResolvedValue(detail), listTicketLogAttachments: vi.fn().mockResolvedValue([]),
  })

  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))
  const stats = await screen.findByRole('region', { name: 'Статистика обращения' })
  const trace = screen.getByRole('region', { name: 'Трассировка агентов' })
  expect(stats.nextElementSibling).toBe(trace)
  expect(within(stats).getByText('62 мс')).toBeVisible()
  expect(within(stats).getByText('122')).toBeVisible()
  expect(within(stats).getByText('21')).toBeVisible()
  const cost = within(stats).getByText('Учтённая стоимость').parentElement!
  expect(within(cost).getByText(/^0,001 \$$/)).toBeVisible()
  expect(within(stats).getByText('2', { exact: true })).toBeVisible()
  expect(within(stats).getAllByText('Данные по шагам с моделью: 2 из 3.')).toHaveLength(2)
  expect(within(stats).getByText('Шагов без записи о запуске: 1.')).toBeVisible()
})

it('distinguishes explicitly recorded zero from missing measurements', async () => {
  const detail: TicketDetail = {
    ...DETAIL,
    steps: [{ ...DETAIL.steps[0]!, run_id: null, duration_ms: 0, tokens_in: 0, tokens_out: null, cost_usd: 0 }],
  }
  renderPage({
    listTickets: vi.fn().mockResolvedValue([TICKET]), getTicketStats: vi.fn().mockResolvedValue(null),
    getTicket: vi.fn().mockResolvedValue(detail), listTicketLogAttachments: vi.fn().mockResolvedValue([]),
  })
  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))

  const stats = await screen.findByRole('region', { name: 'Статистика обращения' })
  expect(within(stats).getByText('0 мс')).toBeVisible()
  const input = within(stats).getByText('Входные токены').parentElement!
  expect(within(input).getByText('0', { exact: true })).toBeVisible()
  expect(within(stats).getByText('Данные по шагам с моделью: 0 из 1.')).toBeVisible()
})

it('shows an empty statistics state before any run or steps exist', async () => {
  renderPage({
    listTickets: vi.fn().mockResolvedValue([TICKET]), getTicketStats: vi.fn().mockResolvedValue(null),
    getTicket: vi.fn().mockResolvedValue({ ...DETAIL, steps: [], runs: [] }),
    listTicketLogAttachments: vi.fn().mockResolvedValue([]),
  })
  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))

  const stats = await screen.findByRole('region', { name: 'Статистика обращения' })
  expect(within(stats).getByText('Статистика появится после записи запуска.')).toBeVisible()
  expect(within(stats).queryByText('Записанные запуски')).not.toBeInTheDocument()
})

it('leaves measured time unavailable for unmeasured terminal and skipped steps', async () => {
  const placeholder = { ...DETAIL.steps[0]!, model_id: null, duration_ms: 0 }
  renderPage({
    listTickets: vi.fn().mockResolvedValue([TICKET]), getTicketStats: vi.fn().mockResolvedValue(null),
    getTicket: vi.fn().mockResolvedValue({
      ...DETAIL,
      steps: [{ ...placeholder, step: 'resolve', status: 'skipped' }, { ...placeholder, step: 'escalate', status: 'completed' }],
    }),
    listTicketLogAttachments: vi.fn().mockResolvedValue([]),
  })
  fireEvent.click(await screen.findByRole('button', { name: /Не работает вход/ }))

  const stats = await screen.findByRole('region', { name: 'Статистика обращения' })
  const duration = within(stats).getByText('Время шагов').parentElement!
  expect(within(duration).getByText('—')).toBeVisible()
})

it('focuses the selected issue on a narrow layout and returns focus to its queue item', async () => {
  const visibleBounds = { length: 1 } as DOMRectList
  const hiddenBounds = { length: 0 } as DOMRectList
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockImplementation(function (this: HTMLElement) {
    return this.classList.contains('issues-back-to-queue') ? visibleBounds : hiddenBounds
  })
  try {
    renderPage({
      listTickets: vi.fn().mockResolvedValue([TICKET]), getTicketStats: vi.fn().mockResolvedValue(null),
      getTicket: vi.fn().mockResolvedValue(DETAIL), listTicketLogAttachments: vi.fn().mockResolvedValue([]),
    })
    const issue = await screen.findByRole('button', { name: /Не работает вход/ })
    fireEvent.click(issue)
    expect(await screen.findByRole('heading', { name: 'Не работает вход' })).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'К списку обращений' }))
    expect(issue).toHaveFocus()
  } finally {
    vi.restoreAllMocks()
  }
})

it('keeps the queue focus when selecting an issue on a wide layout', async () => {
  renderPage({
    listTickets: vi.fn().mockResolvedValue([TICKET]), getTicketStats: vi.fn().mockResolvedValue(null),
    getTicket: vi.fn().mockResolvedValue(DETAIL), listTicketLogAttachments: vi.fn().mockResolvedValue([]),
  })
  const issue = await screen.findByRole('button', { name: /Не работает вход/ })
  issue.focus()
  fireEvent.click(issue)
  await screen.findByRole('heading', { name: 'Не работает вход' })
  expect(issue).toHaveFocus()
})
