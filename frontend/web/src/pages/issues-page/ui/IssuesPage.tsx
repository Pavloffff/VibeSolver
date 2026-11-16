import { useCallback, useEffect, useState } from 'react'
import type { ChangeEvent } from 'react'
import { getApiClient, getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import type { ProjectModelSelections, TicketBrief, TicketDetail, TicketStats, WorkspaceModel } from '../../../shared/api/types'
import { useT } from '../../../shared/i18n'
import type { TranslationKey } from '../../../shared/i18n'
import { parseTicketText } from '../../../features/issues'

interface Props {
  projectId: number
  projectName: string
  api?: ApiClient
}

const STATUS_KEYS: Record<string, TranslationKey> = {
  new: 'issues.statusNew',
  running: 'issues.statusRunning',
  answered: 'issues.statusAnswered',
  escalated: 'issues.statusEscalated',
  failed: 'issues.statusFailed',
}

export default function IssuesPage({ projectId, projectName, api = getApiClient() }: Props) {
  const { t } = useT()
  const [tickets, setTickets] = useState<TicketBrief[]>([])
  const [selected, setSelected] = useState<TicketDetail | null>(null)
  const [chatModels, setChatModels] = useState<WorkspaceModel[]>([])
  const [selections, setSelections] = useState<ProjectModelSelections | null>(null)
  const [stats, setStats] = useState<TicketStats | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const refreshTickets = useCallback(async () => {
    setTickets(await api.listTickets(projectId))
  }, [api, projectId])

  useEffect(() => {
    let cancelled = false
    void refreshTickets().catch((requestError: unknown) => {
      if (!cancelled) setError(getErrorMessage(requestError))
    })
    void Promise.all([api.listWorkspaceModels(), api.getProjectModelSelections(projectId), api.getTicketStats(projectId)])
      .then(([models, modelSelections, ticketStats]) => {
        if (cancelled) return
        setChatModels(models.filter((model) => model.capabilities.includes('chat')))
        setSelections(modelSelections)
        setStats(ticketStats)
      })
      .catch((requestError: unknown) => {
        if (!cancelled) setError(getErrorMessage(requestError))
      })
    return () => { cancelled = true }
  }, [api, projectId, refreshTickets])

  const changeModel = async (role: 'ticket_triage' | 'ticket_resolution' | 'ticket_resolution_cheap', modelId: number | null) => {
    try {
      setSelections(await api.setProjectModelSelection(projectId, role, modelId))
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    }
  }

  const submitTicket = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy('create')
    setError(null)
    setNotice(null)
    try {
      const created = await api.createTicket(projectId, title, description)
      setTitle('')
      setDescription('')
      await refreshTickets()
      setSelected(await api.getTicket(created.id))
    } catch (createError) {
      setError(getErrorMessage(createError))
    } finally {
      setBusy(null)
    }
  }

  const importTicketText = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget
    const file = input.files?.[0]
    if (file === undefined) return

    setError(null)
    if (!file.name.toLowerCase().endsWith('.txt')) {
      setError(t('issues.importTextInvalidType'))
      input.value = ''
      return
    }

    try {
      const parsed = parseTicketText(await file.text())
      if (parsed === null || parsed.title.length < 3 || parsed.title.length > 200 || parsed.description.length < 10 || parsed.description.length > 20000) {
        setError(t('issues.importTextInvalidContent'))
        return
      }
      setTitle(parsed.title)
      setDescription(parsed.description)
    } catch {
      setError(t('issues.importTextReadError'))
    } finally {
      input.value = ''
    }
  }

  const runTicket = async (ticketId: number) => {
    setBusy(`run-${ticketId}`)
    setError(null)
    setNotice(null)
    try {
      const detail = await api.runTicket(ticketId)
      setSelected(detail)
      await Promise.all([refreshTickets(), api.getTicketStats(projectId).then(setStats)])
      setNotice(detail.ticket.status === 'answered' ? t('issues.answerReady') : t('issues.escalatedNotice'))
    } catch (runError) {
      setError(getErrorMessage(runError))
      try { await refreshTickets() } catch { /* keep the visible error */ }
    } finally {
      setBusy(null)
    }
  }

  const openTicket = async (ticketId: number) => {
    try {
      setSelected(await api.getTicket(ticketId))
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    }
  }

  const canRun = (status: string) => status !== 'running'
  const modelPicker = (label: string, role: 'ticket_triage' | 'ticket_resolution' | 'ticket_resolution_cheap', modelId: number | null | undefined) => (
    <label className="generation-model-picker" key={role}>{label}
      <select
        value={modelId ?? ''}
        disabled={chatModels.length === 0}
        onChange={(event) => void changeModel(role, event.target.value ? Number(event.target.value) : null)}
      >
        <option value="">{t(chatModels.length === 0 ? 'materials.noChatModels' : 'issues.selectModel')}</option>
        {chatModels.map((model) => (
          <option key={model.id} value={model.id}>{model.display_name} · {model.provider_name}</option>
        ))}
      </select>
    </label>
  )

  return (
    <div className="issues-page">
      <div className="page-header">
        <div>
          <span className="eyebrow">{projectName}</span>
          <h1>{t('project.issues')}</h1>
          <p>{t('issues.pageDescription')}</p>
        </div>
        <div className="issues-model-pickers">
          {modelPicker(t('issues.triageModel'), 'ticket_triage', selections?.ticket_triage)}
          {modelPicker(t('issues.resolutionModel'), 'ticket_resolution', selections?.ticket_resolution)}
          {modelPicker(t('issues.cheapModel'), 'ticket_resolution_cheap', selections?.ticket_resolution_cheap)}
        </div>
      </div>

      {error !== null && <div className="error page-alert" role="alert">{error}</div>}
      {notice !== null && <div className="success-note models-notice" role="status">{notice}</div>}

      {stats !== null && (
        <section className="project-card issues-stats" aria-label={t('issues.statsTitle')}>
          <div className="project-card-heading"><div><h2>{t('issues.statsTitle')}</h2><p>{t('issues.statsHint')}</p></div></div>
          <div className="provider-card-meta">
            <span><strong>{t('issues.autoresolveRate')}</strong> {Math.round(stats.autoresolve_rate * 100)}%</span>
            <span><strong>{t('issues.averageCost')}</strong> {stats.avg_cost_usd === null ? '—' : `$${stats.avg_cost_usd.toFixed(4)}`}</span>
            <span><strong>{t('issues.tokenUsage')}</strong> {stats.tokens_in.toLocaleString()} / {stats.tokens_out.toLocaleString()}</span>
            <span><strong>{t('issues.averageTokens')}</strong> {Math.round(stats.avg_tokens_per_ticket).toLocaleString()}</span>
          </div>
        </section>
      )}

      <form className="project-card issues-create-form" onSubmit={submitTicket}>
        <label>{t('issues.importTextFile')}<input type="file" accept=".txt,text/plain" onChange={(event) => void importTicketText(event)} /></label>
        <p className="field-hint">{t('issues.importTextHint')}</p>
        <label>{t('issues.titleLabel')}<input required minLength={3} maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <label>{t('issues.descriptionLabel')}<textarea required minLength={10} maxLength={20000} rows={4} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <button type="submit" className="btn btn-primary" disabled={busy !== null}>{busy === 'create' ? t('project.uploading') : `+ ${t('project.addIssue')}`}</button>
      </form>

      <section className="project-card">
        <div className="project-card-heading"><div><h2>{t('issues.listTitle')}</h2><p>{t('issues.listHint')}</p></div></div>
        {tickets.length === 0 ? (
          <p className="resource-empty">{t('project.noIssues')}</p>
        ) : (
          <div className="issues-ticket-list">
            {tickets.map((ticket) => (
              <div className="issues-ticket-row" key={ticket.id}>
                <button type="button" className="issues-ticket-open" onClick={() => void openTicket(ticket.id)}>
                  <strong>{ticket.title}</strong>
                  <span className={`badge issue-state-${ticket.status}`}>
                    {t(STATUS_KEYS[ticket.status] ?? 'issues.statusNew' as TranslationKey)}
                  </span>
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy !== null || !canRun(ticket.status)}
                  onClick={() => void runTicket(ticket.id)}
                >
                  {busy === `run-${ticket.id}` ? t('issues.running') : ticket.status === 'new' ? t('issues.run') : t('issues.rerun')}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {selected !== null && (
        <section className="project-card issues-ticket-detail">
          <div className="project-card-heading">
            <div>
              <h2>{selected.ticket.title}</h2>
              <p>{selected.ticket.description}</p>
              {selected.ticket.triage !== null && (
                <div className="provider-card-meta">
                  {typeof selected.ticket.triage.category === 'string' && <span className="badge">{String(selected.ticket.triage.category)}</span>}
                  {typeof selected.ticket.triage.severity === 'string' && <span className="badge">{String(selected.ticket.triage.severity)}</span>}
                  {typeof selected.ticket.triage.summary === 'string' && <span>{String(selected.ticket.triage.summary)}</span>}
                </div>
              )}
            </div>
            <button type="button" className="text-button" onClick={() => setSelected(null)} aria-label={t('common.cancel')}>×</button>
          </div>

          {selected.ticket.status === 'answered' && selected.ticket.answer !== null && (
            <div className="issues-answer">
              <h3>{t('issues.answerTitle')}</h3>
              <div className="issues-answer-body">{selected.ticket.answer}</div>
              {selected.ticket.citations.length > 0 && (
                <div className="issues-citations">
                  <h4>{t('issues.sources')}</h4>
                  <ul>
                    {selected.ticket.citations.map((citation) => (
                      <li key={citation.source_ref}>
                        <code>{citation.path}</code>
                        {citation.start_line !== null && <span>:{citation.start_line}</span>}
                        <span className="badge">{citation.index_type}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {(selected.ticket.status === 'escalated' || selected.ticket.status === 'failed') && selected.ticket.escalate_reason !== null && (
            <div className="issues-escalation">
              <strong>{t('issues.escalateTitle')}</strong>
              <p>{selected.ticket.escalate_reason}</p>
              {selected.ticket.citations.length > 0 && (
                <details>
                  <summary>{t('issues.dossier')}</summary>
                  <ul>
                    {selected.ticket.citations.map((citation) => (
                      <li key={citation.source_ref}><code>{citation.path}</code>{citation.start_line !== null && <span>:{citation.start_line}</span>}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}

          <details className="issues-trace">
            <summary>{t('issues.trace')}</summary>
            <ol>
              {selected.steps.map((step, index) => (
                <li key={index}>
                  <strong>{step.step}</strong>
                  {step.duration_ms > 0 && <span> · {step.duration_ms} ms</span>}
                  {(step.tokens_in !== null || step.tokens_out !== null) && <span> · {step.tokens_in ?? 0} / {step.tokens_out ?? 0} tokens</span>}
                  {step.cost_usd !== null && <span> · ${step.cost_usd.toFixed(6)}</span>}
                  <pre>{JSON.stringify(step.output_data, null, 2)}</pre>
                </li>
              ))}
            </ol>
          </details>
        </section>
      )}
    </div>
  )
}
