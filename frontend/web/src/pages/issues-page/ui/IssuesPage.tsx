import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { getApiClient, getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import type { SolverGraph, TicketBrief, TicketDetail, TicketStats } from '../../../shared/api/types'
import { useT } from '../../../shared/i18n'
import type { TranslationKey } from '../../../shared/i18n'
import { parseTicketText } from '../../../features/issues'
import TicketLogAttachments from '../../../features/ticket-log-attachments'

interface Props {
  projectId: number
  projectName: string
  api?: ApiClient
  active?: boolean
  onOpenSolver?: () => void
}

const STATUS_KEYS: Record<string, TranslationKey> = {
  new: 'issues.statusNew',
  running: 'issues.statusRunning',
  answered: 'issues.statusAnswered',
  escalated: 'issues.statusEscalated',
  failed: 'issues.statusFailed',
}
const STEP_KEYS: Record<string, TranslationKey> = {
  triage: 'issues.stepTriage', investigate: 'issues.stepInvestigate', resolve: 'issues.stepResolve',
  answer: 'issues.stepAnswer', escalate: 'issues.stepEscalate',
}
const STEP_STATUS_KEYS: Record<string, TranslationKey> = {
  completed: 'issues.stepCompleted', skipped: 'issues.stepSkipped', failed: 'issues.stepFailed',
  running: 'issues.statusRunning', answered: 'issues.statusAnswered', escalated: 'issues.statusEscalated',
}
const MODEL_ROLE_KEYS: Record<string, TranslationKey> = {
  ticket_triage: 'issues.triageModel', ticket_resolution: 'issues.resolutionModel', ticket_resolution_cheap: 'issues.cheapModel',
}

export default function IssuesPage({ projectId, projectName, api = getApiClient(), active = true, onOpenSolver }: Props) {
  const { t, lang } = useT()
  const [graph, setGraph] = useState<SolverGraph | null>(null)
  const [indexReady, setIndexReady] = useState<boolean | null>(typeof api.getProjectIndexStatus === 'function' ? null : true)
  const [profileId, setProfileId] = useState<number | null>(null)
  const [tickets, setTickets] = useState<TicketBrief[]>([])
  const [selected, setSelected] = useState<TicketDetail | null>(null)
  const [stats, setStats] = useState<TicketStats | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [blockedLogTickets, setBlockedLogTickets] = useState<Record<number, boolean>>({})
  const selectionRequest = useRef(0)

  const updateLogBlocked = useCallback((ticketId: number, blocked: boolean) => {
    setBlockedLogTickets((current) => ({ ...current, [ticketId]: blocked }))
  }, [])

  const refreshTickets = useCallback(async () => {
    setTickets(await api.listTickets(projectId))
  }, [api, projectId])

  useEffect(() => {
    if (!active || typeof api.getSolverGraph !== 'function') return
    let cancelled = false
    setGraph(null)
    setProfileId(null)
    void api.getSolverGraph(projectId).then((value) => {
      if (cancelled) return
      setGraph(value)
    }).catch((requestError: unknown) => { if (!cancelled) setError(getErrorMessage(requestError)) })
    return () => { cancelled = true }
  }, [active, api, projectId])

  useEffect(() => {
    if (!active || typeof api.getProjectIndexStatus !== 'function') return
    let cancelled = false
    setIndexReady(null)
    void api.getProjectIndexStatus(projectId).then((status) => { if (!cancelled) setIndexReady(status.ready) }).catch((requestError: unknown) => { if (!cancelled) setError(getErrorMessage(requestError)) })
    return () => { cancelled = true }
  }, [active, api, projectId])

  useEffect(() => {
    let cancelled = false
    void refreshTickets().catch((requestError: unknown) => {
      if (!cancelled) setError(getErrorMessage(requestError))
    })
    void api.getTicketStats(projectId)
      .then((ticketStats) => {
        if (cancelled) return
        setStats(ticketStats)
      })
      .catch((requestError: unknown) => {
        if (!cancelled) setError(getErrorMessage(requestError))
      })
    return () => { cancelled = true }
  }, [api, projectId, refreshTickets])

  const submitTicket = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy('create')
    setError(null)
    setNotice(null)
    try {
      const created = await api.createTicket(projectId, title, description)
      setTitle('')
      setDescription('')
      setProfileId(null)
      await refreshTickets()
      setSelected(await api.getTicket(created.id))
    } catch (createError) {
      setError(getErrorMessage(createError))
    } finally {
      setProfileId(null)
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
      const attachments = await api.listTicketLogAttachments(ticketId)
      const hasUnreadyLogs = attachments.some((item) => item.status !== 'ready')
      updateLogBlocked(ticketId, hasUnreadyLogs)
      if (hasUnreadyLogs) {
        setSelected(await api.getTicket(ticketId))
        setError(t('issues.logsNotReady'))
        return
      }
      const detail = profileId === null ? await api.runTicket(ticketId) : await api.runTicket(ticketId, profileId)
      setProfileId(null)
      setSelected(detail)
      await Promise.all([refreshTickets(), api.getTicketStats(projectId).then(setStats)])
      setNotice(detail.ticket.status === 'answered' ? t('issues.answerReady') : t('issues.escalatedNotice'))
    } catch (runError) {
      setError(getErrorMessage(runError))
      try { setSelected(await api.getTicket(ticketId)) } catch { /* keep the visible error */ }
      try { await refreshTickets() } catch { /* keep the visible error */ }
    } finally {
      setProfileId(null)
      setBusy(null)
    }
  }

  const openTicket = async (ticketId: number) => {
    const request = ++selectionRequest.current
    setProfileId(null)
    setSelected(null)
    try {
      const detail = await api.getTicket(ticketId)
      if (request === selectionRequest.current) setSelected(detail)
    } catch (requestError) {
      if (request === selectionRequest.current) setError(getErrorMessage(requestError))
    }
  }

  const canRun = (ticketId: number, status: string, hasUnreadyLogs?: boolean) =>
    indexReady === true && (typeof api.getSolverGraph !== 'function' || (graph !== null && graph.profiles.some((profile) => profile.id === (profileId ?? graph.default_profile_id)))) && status !== 'running' && hasUnreadyLogs !== true && blockedLogTickets[ticketId] !== true
  return (
    <div className="issues-page">
      <div className="page-header">
        <div>
          <span className="eyebrow">{projectName}</span>
          <h1>{t('project.issues')}</h1>
          <p>{t('issues.pageDescription')}</p>
        </div>
        {onOpenSolver && selected === null && <button type="button" className="btn" onClick={onOpenSolver}>{t('solver.title')}</button>}
      </div>

      {error !== null && <div className="error page-alert" role="alert">{error}</div>}
      {notice !== null && <div className="success-note models-notice" role="status">{notice}</div>}
      {indexReady === false && <p className="field-hint">{t('project.finishIndexingBeforeIssues')}</p>}

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

      <details className="issues-intake" open={tickets.length === 0}><summary>{t('project.addIssue')}</summary><form className="project-card issues-create-form" onSubmit={submitTicket}>
        <label>{t('issues.importTextFile')}<input type="file" accept=".txt,text/plain" onChange={(event) => void importTicketText(event)} /></label>
        <p className="field-hint">{t('issues.importTextHint')}</p>
        <label>{t('issues.titleLabel')}<input required minLength={3} maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <label>{t('issues.descriptionLabel')}<textarea required minLength={10} maxLength={20000} rows={4} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <button type="submit" className="btn btn-primary" disabled={busy !== null}>{busy === 'create' ? t('project.uploading') : `+ ${t('project.addIssue')}`}</button>
      </form></details>

      <div className={`issues-workspace${selected === null ? ' issues-workspace-empty' : ' issues-workspace-selected'}`}><section className="project-card issues-queue">
        <div className="project-card-heading"><div><h2>{t('issues.listTitle')}</h2><p>{t('issues.listHint')}</p></div></div>
        {tickets.length === 0 ? (
          <p className="resource-empty">{t('project.noIssues')}</p>
        ) : (
          <div className="issues-ticket-list">
            {tickets.map((ticket) => (
              <div className="issues-ticket-row" key={ticket.id}>
                <button type="button" className="issues-ticket-open" disabled={busy !== null} onClick={() => void openTicket(ticket.id)}>
                  <strong>{ticket.title}</strong>
                  <span className={`badge issue-state-${ticket.status}`}>
                    {t(STATUS_KEYS[ticket.status] ?? 'issues.statusNew' as TranslationKey)}
                  </span>
                </button>
              </div>
            ))}
          </div>


        )}
      </section>

      {selected !== null && (
        <section className="project-card issues-ticket-detail">
          <button type="button" className="text-button issues-mobile-back" disabled={busy !== null} onClick={() => { selectionRequest.current++; setSelected(null); setProfileId(null) }}>{t('issues.backToQueue')}</button>
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
            <button type="button" className="text-button" disabled={busy !== null} onClick={() => { selectionRequest.current++; setSelected(null); setProfileId(null) }} aria-label={t('common.cancel')}>×</button>
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

          <div className="issues-run-controls">
            {graph !== null && <label className="generation-model-picker">{t('issues.profile')}<select value={profileId ?? ''} onChange={(event) => setProfileId(event.target.value === '' ? null : Number(event.target.value))}><option value="">{t('issues.projectDefault', { name: graph.profiles.find((profile) => profile.id === graph.default_profile_id)?.name ?? t('issues.unavailable') })}</option>{graph.profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select></label>}
            {onOpenSolver && <button type="button" className="text-button" onClick={onOpenSolver}>{t('solver.title')}</button>}
            <button type="button" className="btn btn-primary" disabled={busy !== null || !canRun(selected.ticket.id, selected.ticket.status, tickets.find((ticket) => ticket.id === selected.ticket.id)?.has_unready_log_attachments)} onClick={() => void runTicket(selected.ticket.id)}>{busy === `run-${selected.ticket.id}` ? t('issues.running') : selected.ticket.status === 'new' ? t('issues.run') : t('issues.rerun')}</button>
          </div>

          <TicketLogAttachments
            ticketId={selected.ticket.id}
            api={api}
            onUnreadyChange={updateLogBlocked}
          />

          <details className="issues-trace">
            <summary>{t('issues.trace')}</summary>
            {(selected.runs ?? []).map((run) => <section className="issues-run" key={run.id}>
              <h4>{run.profile_name} · {STATUS_KEYS[run.status] ? t(STATUS_KEYS[run.status]!) : STEP_STATUS_KEYS[run.status] ? t(STEP_STATUS_KEYS[run.status]!) : run.status}</h4><p>{new Date(run.created_at).toLocaleString(lang)}</p>
              {run.error && <p role="alert">{run.error}</p>}
              <dl>{Object.entries(run.models).map(([role, model]) => <div key={role}><dt>{MODEL_ROLE_KEYS[role] ? t(MODEL_ROLE_KEYS[role]!) : role}</dt><dd>{model?.display_name ?? t('issues.unavailable')}</dd></div>)}</dl>
              <TraceSteps steps={selected.steps.filter((step) => step.run_id === run.id)} models={run.models} />
            </section>)}
            {selected.steps.some((step) => step.run_id == null) && <section><h4>{t('issues.historicalRun')}</h4><TraceSteps steps={selected.steps.filter((step) => step.run_id == null)} /></section>}
            {selected.steps.length === 0 && <p>{t('issues.unavailable')}</p>}
          </details>
        </section>
      )}</div>
    </div>
  )
}

function ReadableValue({ value }: { value: unknown }) {
  const { t } = useT()
  if (value === null || value === undefined) return <span>—</span>
  if (value === 'disabled_by_profile') return <span>{t('issues.disabledByProfile')}</span>
  if (Array.isArray(value)) return <ul>{value.map((item, index) => <li key={index}><ReadableValue value={item} /></li>)}</ul>
  const labels: Record<string, TranslationKey> = { summary: 'issues.fieldSummary', answer: 'issues.answerTitle', reason: 'issues.fieldReason', error: 'issues.stepFailed', category: 'issues.fieldCategory', severity: 'issues.fieldSeverity', evidence: 'issues.sources', refs: 'issues.sources', path: 'issues.fieldPath' }
  if (typeof value === 'object') return <dl>{Object.entries(value).filter(([key]) => !/password|secret|token|credential|api.?key|authorization/i.test(key)).map(([key, item]) => <div key={key}><dt>{labels[key] ? t(labels[key]!) : key.replaceAll('_', ' ')}</dt><dd><ReadableValue value={item} /></dd></div>)}</dl>
  return <span>{String(value)}</span>
}

function TraceSteps({ steps, models }: { steps: TicketDetail['steps']; models?: NonNullable<TicketDetail['runs']>[number]['models'] }) {
  const { t } = useT()
  const count = (value: unknown): number | null => typeof value === 'number' ? value : Array.isArray(value) ? value.length : value && typeof value === 'object' ? Object.keys(value).length : null
  return <ol className="issues-step-list">{steps.map((step, index) => {
    const fragments = count(step.output_data.fragments)
    const refs = count(step.output_data.refs)
    const message = ['summary', 'answer', 'escalate_reason', 'reason', 'error', 'category'].map((key) => step.output_data[key]).find((value) => typeof value === 'string') as string | undefined
    const summary = message === 'disabled_by_profile' ? t('issues.disabledByProfile') : message
    return <li key={index} className={`issues-step issues-step-${step.status ?? 'unknown'}`}>
    <div className="issues-step-heading"><strong>{STEP_KEYS[step.step] ? t(STEP_KEYS[step.step]!) : step.step.replaceAll('_', ' ')}</strong><span>{step.status && STEP_STATUS_KEYS[step.status] ? t(STEP_STATUS_KEYS[step.status]!) : t('issues.unavailable')}</span></div>
    <div className="issues-step-metrics">{t('issues.model')}: {Object.values(models ?? {}).find((model) => model?.id === step.model_id)?.display_name ?? step.model_id ?? t('issues.unavailable')}
    {step.status !== 'skipped' && <span> · {t('issues.duration', { value: String(step.duration_ms) })}</span>}
    <span> · {t('issues.tokenUsage')}: {step.tokens_in ?? '—'} / {step.tokens_out ?? '—'}</span>
    <span> · {t('issues.stepCost')}: {step.cost_usd === null ? '—' : `$${step.cost_usd.toFixed(6)}`}</span>
    </div>
    <p className="issues-step-summary">{[summary, fragments !== null ? t('issues.fragmentsCount', { count: String(fragments) }) : null, refs !== null ? t('issues.refsCount', { count: String(refs) }) : null].filter(Boolean).join(' · ') || (step.status === 'skipped' ? t('issues.stepSkipped') : t('issues.traceDetails'))}</p>
    <details><summary>{t('issues.traceInput')}</summary><ReadableValue value={step.input_data} /></details>
    <details><summary>{t('issues.traceOutput')}</summary><ReadableValue value={step.output_data} /></details>
  </li>})}</ol>
}
