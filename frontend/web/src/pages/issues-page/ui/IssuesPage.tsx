import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getApiClient, getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import type { SolverGraph, TicketBrief, TicketCitation, TicketDetail, TicketStats } from '../../../shared/api/types'
import { useT } from '../../../shared/i18n'
import type { TranslationKey } from '../../../shared/i18n'
import TicketLogAttachments from '../../../features/ticket-log-attachments'
import IssueIntake from './IssueIntake'
import IssueRunStats from './IssueRunStats'
import { useLocalizedOutcome } from './useLocalizedOutcome'
import '../../../styles/issues.css'

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
  answered: 'issueWorkspace.suggestionStatus',
  escalated: 'issues.statusEscalated',
  failed: 'issues.statusFailed',
}
const STEP_KEYS: Record<string, TranslationKey> = {
  log_intake: 'solver.logIntake', read_code: 'solver.readCode', recheck: 'solver.recheck',
  triage: 'issues.stepTriage', investigate: 'issues.stepInvestigate', resolve: 'issues.stepResolve',
  answer: 'issues.stepAnswer', escalate: 'issues.stepEscalate',
  flow: 'solver.flowAgent', logs: 'solver.logsAgent', code: 'solver.codeAgent',
  ui: 'solver.uiAgent', web: 'solver.webAgent', review: 'solver.reviewAgent',
  web_search: 'issues.diagnosticWebSearchStep',
}
const STEP_STATUS_KEYS: Record<string, TranslationKey> = {
  completed: 'issues.stepCompleted', skipped: 'issues.stepSkipped', failed: 'issues.stepFailed',
  running: 'issues.statusRunning', answered: 'issueWorkspace.suggestionStatus', escalated: 'issues.statusEscalated',
}
const MODEL_ROLE_KEYS: Record<string, TranslationKey> = {
  ticket_triage: 'issues.triageModel', ticket_resolution: 'issues.resolutionModel', ticket_resolution_cheap: 'issues.cheapModel',
}

const SOURCE_KEYS: Record<string, TranslationKey> = {
  code: 'project.indexCode',
  documentation: 'project.indexDocumentation',
  user_flow: 'project.indexUserFlow',
  external_web: 'issues.diagnosticWebSearchSource',
  ui_observation: 'issues.observationTitle',
  logs: 'issueWorkspace.logSource',
  'ticket-log': 'issueWorkspace.logSource',
  ticket_history: 'issueWorkspace.historySource',
}
const SEVERITY_KEYS: Record<string, TranslationKey> = {
  low: 'issueWorkspace.severityLow',
  medium: 'issueWorkspace.severityMedium',
  high: 'issueWorkspace.severityHigh',
  critical: 'issueWorkspace.severityCritical',
}
const TRACE_FIELD_KEYS: Record<string, TranslationKey> = {
  summary: 'issues.fieldSummary', answer: 'issueWorkspace.suggestion', reason: 'issues.fieldReason',
  error: 'issues.stepFailed', category: 'issues.fieldCategory', severity: 'issues.fieldSeverity',
  evidence: 'issues.sources', refs: 'issues.sources', source_refs: 'issues.sources',
  path: 'issues.fieldPath', title: 'issues.titleLabel', description: 'issues.descriptionLabel',
  complexity: 'issueWorkspace.complexity', search_queries: 'issueWorkspace.searchQueries',
  queries: 'issueWorkspace.searchQueries', missing_info: 'issueWorkspace.missingInfo',
  specialists: 'issueWorkspace.specialists', finding: 'issueWorkspace.finding',
  follow_up_query: 'issueWorkspace.followUpQuery', search_status: 'issueWorkspace.searchStatus',
  targeted_search: 'issueWorkspace.targetedSearch', localization_status: 'issueWorkspace.localizationStatus',
  query_origin: 'issueWorkspace.queryOrigin', files: 'issueWorkspace.files',
  decision: 'issueWorkspace.decision', routing: 'issueWorkspace.routing', tier: 'issueWorkspace.tier',
  rerun_context: 'issueWorkspace.rerunContext', previous_outcome: 'issueWorkspace.previousOutcome',
  previous_result: 'issueWorkspace.previousOutcome', previous_status: 'issueWorkspace.previousStatus',
  comment: 'issueWorkspace.comment', observations: 'issueWorkspace.observations',
  approved: 'issueWorkspace.approved', fragments: 'issueWorkspace.fragments',
  index_type: 'issueWorkspace.source', start_line: 'issueWorkspace.startLine', end_line: 'issueWorkspace.endLine',
  role: 'issueWorkspace.observationRole', name: 'issueWorkspace.observationName',
  width: 'issueWorkspace.observationWidth', height: 'issueWorkspace.observationHeight',
  visible: 'issueWorkspace.observationVisible', enabled: 'issueWorkspace.observationEnabled',
  checked: 'issueWorkspace.observationChecked', observed_at: 'issueWorkspace.observationDate',
  status: 'issueWorkspace.status', escalate_reason: 'issues.fieldReason',
  skipped_llm: 'issueWorkspace.skippedLlm', error_type: 'issueWorkspace.fieldErrorType',
  origin: 'issueWorkspace.fieldOrigin', event_timestamp: 'issueWorkspace.fieldEventTime',
  source_ref: 'issueWorkspace.sourceRef', ticket_id: 'issueWorkspace.ticketId',
  attachment_id: 'issueWorkspace.attachmentId', label: 'issueWorkspace.fieldLabel',
  runtime_facts: 'issueWorkspace.runtimeFacts', field: 'issueWorkspace.factField', value: 'issueWorkspace.factValue',
  indexes_searched: 'issueWorkspace.indexesSearched', scope: 'issueWorkspace.evidenceScope',
}
const SEARCH_STATUS_KEYS: Record<string, TranslationKey> = {
  ...STEP_STATUS_KEYS, partial: 'issueWorkspace.partial', empty: 'issueWorkspace.empty',
  unavailable: 'issues.unavailable', no_new_evidence: 'issueWorkspace.noNewEvidence',
}
const TRACE_VALUE_KEYS: Record<string, Record<string, TranslationKey>> = {
  severity: SEVERITY_KEYS,
  index_type: SOURCE_KEYS,
  indexes_searched: SOURCE_KEYS,
  scope: { current_ticket: 'issueWorkspace.scopeCurrentTicket' },
  field: {
    service_version: 'issueWorkspace.factServiceVersion', environment: 'issueWorkspace.factEnvironment',
    platform: 'issueWorkspace.factPlatform', namespace: 'issueWorkspace.factNamespace',
    cluster_version: 'issueWorkspace.factClusterVersion', image_tag: 'issueWorkspace.factImageTag',
  },
  complexity: { simple: 'issueWorkspace.simple', standard: 'issueWorkspace.standard', hard: 'issueWorkspace.hard' },
  status: {
    ...STATUS_KEYS, ...STEP_STATUS_KEYS, supported: 'issueWorkspace.supported',
    gap: 'issueWorkspace.gap', disputed: 'issueWorkspace.disputed',
  },
  search_status: SEARCH_STATUS_KEYS,
  targeted_search: SEARCH_STATUS_KEYS,
  tier: { cheap: 'issueWorkspace.budgetTier', strong: 'issueWorkspace.primaryTier' },
  localization_status: STEP_STATUS_KEYS,
  previous_status: STATUS_KEYS,
  query_origin: { ticket: 'issueWorkspace.originTicket', triage: 'issueWorkspace.originTriage' },
  decision: { answer: 'issueWorkspace.decisionAnswer', escalate: 'issueWorkspace.decisionEscalate' },
  specialists: STEP_KEYS,
  reason: {
    'simple ticket routed to the configured low-cost model': 'issueWorkspace.routingSimple',
    'standard or hard ticket routed to the strong model': 'issueWorkspace.routingComplex',
    'no low-cost model is configured; using the strong model': 'issueWorkspace.routingNoBudget',
    'triage is disabled; using the strong model': 'issueWorkspace.routingTriageOff',
    'Internal evidence was sufficient': 'issueWorkspace.diagnosticEvidenceSufficient',
    'The ticket is outside the project scope.': 'issueWorkspace.diagnosticOutsideProject',
    'The project has no configured UI probe.': 'issueWorkspace.diagnosticNoUiProbe',
    'The test stand UI observation failed.': 'issueWorkspace.diagnosticUiProbeFailed',
    'Web search is disabled for this project.': 'issueWorkspace.diagnosticWebDisabled',
    'The project has no configured web provider.': 'issueWorkspace.diagnosticNoWebProvider',
    'No approved public error signature was found.': 'issueWorkspace.diagnosticNoPublicSignature',
  },
}

export default function IssuesPage({ projectId, projectName, api = getApiClient(), active = true, onOpenSolver }: Props) {
  const { t, lang } = useT()
  const [graph, setGraph] = useState<SolverGraph | null>(null)
  const [indexReady, setIndexReady] = useState<boolean | null>(typeof api.getProjectIndexStatus === 'function' ? null : true)
  const [profileId, setProfileId] = useState<number | null>(null)
  const [tickets, setTickets] = useState<TicketBrief[]>([])
  const [selected, setSelected] = useState<TicketDetail | null>(null)
  const outcome = useLocalizedOutcome(selected?.ticket ?? null, api, active)
  const displayedOutcome = outcome.text ?? <div role="status">
    {t(outcome.unavailable ? 'issueWorkspace.translationUnavailable' : 'issueWorkspace.translating')}
    {outcome.unavailable && <> <button type="button" className="text-button" onClick={outcome.retry}>{t('solver.retry')}</button></>}
  </div>
  const [stats, setStats] = useState<TicketStats | null>(null)
  const [rerunComment, setRerunComment] = useState('')
  const [intakeBusy, setIntakeBusy] = useState(false)
  const [mutatingLogs, setMutatingLogs] = useState(false)
  const [copyFeedback, setCopyFeedback] = useState<{ section: 'trace' | 'answer'; success: boolean } | null>(null)
  const traceContent = useRef<HTMLDivElement>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [blockedLogTickets, setBlockedLogTickets] = useState<Record<number, boolean>>({})
  const selectionRequest = useRef(0)
  const detailTitle = useRef<HTMLHeadingElement>(null)
  const backToQueue = useRef<HTMLButtonElement>(null)
  const queue = useRef<HTMLElement>(null)
  const focusOnOpen = useRef(false)
  const returnFocus = useRef<{ ticketId: number; scroll: boolean } | null>(null)
  const selectedId = selected?.ticket.id

  useLayoutEffect(() => {
    if (selectedId !== undefined) {
      if (focusOnOpen.current && backToQueue.current?.getClientRects().length) {
        detailTitle.current?.focus({ preventScroll: true })
        backToQueue.current.scrollIntoView?.({ block: 'start' })
      }
      focusOnOpen.current = false
    } else if (returnFocus.current !== null) {
      const { ticketId, scroll } = returnFocus.current
      returnFocus.current = null
      const trigger = queue.current?.querySelector<HTMLButtonElement>(`[data-issue-id="${ticketId}"]`)
      trigger?.focus({ preventScroll: true })
      if (scroll) trigger?.scrollIntoView?.({ block: 'nearest' })
    }
  }, [selectedId])
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

  const handleCreated = async (ticketId: number) => {
    selectionRequest.current++
    setError(null)
    setNotice(null)
    setProfileId(null)
    setRerunComment('')
    setCopyFeedback(null)
    await Promise.all([
      api.getTicket(ticketId).then(setSelected),
      refreshTickets(),
      api.getTicketStats(projectId).then(setStats),
    ])
  }

  const copy = async (section: 'trace' | 'answer', text: string) => {
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(text)
      } else {
        const active = document.activeElement
        const field = document.createElement('textarea')
        field.value = text
        field.readOnly = true
        field.className = 'issues-clipboard-field'
        document.body.append(field)
        try {
          field.select()
          if (!document.execCommand('copy')) throw new Error('Copy command failed')
        } finally {
          field.remove()
          if (active instanceof HTMLElement) active.focus()
        }
      }
      setCopyFeedback({ section, success: true })
    } catch {
      setCopyFeedback({ section, success: false })
    }
  }

  const copyTrace = () => {
    const content = traceContent.current
    if (content === null) return
    const text = content.innerText ?? Array.from(content.querySelectorAll('h4,h5,h6,p,dt,dd,.issues-step-heading,.issues-step-metrics'))
      .map((element) => element.textContent ?? '')
      .join('\n')
    void copy('trace', text.trim())
  }

  const runTicket = async (ticketId: number, runProfileId: number) => {
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
      const comment = rerunComment.trim()
      const detail = comment
        ? await api.runTicket(ticketId, runProfileId, comment)
        : await api.runTicket(ticketId, runProfileId)
      setRerunComment('')
      setCopyFeedback(null)
      setProfileId(null)
      setSelected(detail)
      await Promise.all([refreshTickets(), api.getTicketStats(projectId).then(setStats)])
      if (detail.ticket.status === 'answered') setNotice(t('issueWorkspace.suggestionReady'))
      if (detail.ticket.status === 'escalated') setNotice(t('issues.escalatedNotice'))
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
    setRerunComment('')
    setCopyFeedback(null)
    setSelected(null)
    setError(null)
    setNotice(null)
    try {
      const detail = await api.getTicket(ticketId)
      if (request === selectionRequest.current) {
        focusOnOpen.current = true
        setSelected(detail)
      }
    } catch (requestError) {
      if (request === selectionRequest.current) setError(getErrorMessage(requestError))
    }
  }

  const selectedProfile = graph?.profiles.find(profile => profile.id === profileId)
  const evidenceReady = indexReady === true || selectedProfile?.enabled?.ui === true
  const interactionBusy = busy !== null || intakeBusy || mutatingLogs
  const canRun = (ticketId: number, status: string) =>
    evidenceReady && selectedProfile !== undefined && status !== 'running' &&
    !(blockedLogTickets[ticketId] ?? tickets.find((ticket) => ticket.id === ticketId)?.has_unready_log_attachments)
  const closeDetail = () => {
    if (selectedId !== undefined) {
      returnFocus.current = { ticketId: selectedId, scroll: Boolean(backToQueue.current?.getClientRects().length) }
    }
    selectionRequest.current++
    setSelected(null)
    setProfileId(null)
    setRerunComment('')
    setCopyFeedback(null)
  }

  return (
    <div className="issues-page">
      <header className="page-header issues-header">
        <div>
          <span className="eyebrow">{projectName}</span>
          <h1>{t('project.issues')}</h1>
          <p>{t('issueWorkspace.pageDescription')}</p>
        </div>
        <IssueIntake key={projectId} api={api} projectId={projectId} disabled={busy !== null || mutatingLogs} onBusyChange={setIntakeBusy} onCreated={handleCreated} />
      </header>
      {error !== null && <div className="error page-alert" role="alert">{error}</div>}
      {notice !== null && <div className="success-note models-notice" role="status">{notice}</div>}
      {indexReady === false && !evidenceReady && <p className="field-hint">{t('project.finishIndexingBeforeIssues')}</p>}

      {stats !== null && (
        <section className="project-card issues-stats" aria-labelledby="issues-stats-title">
          <header className="issues-panel-heading"><h2 id="issues-stats-title">{t('issues.statsTitle')}</h2></header>
          <dl className="issues-stats-grid">
            <div title={t('issueWorkspace.statsHint')}><dt>{t('issueWorkspace.suggestionRate')}</dt><dd>{Math.round(stats.autoresolve_rate * 100)}%</dd></div>
            <div><dt>{t('issues.averageCost')}</dt><dd>{stats.avg_cost_usd === null ? '—' : `$${stats.avg_cost_usd.toFixed(4)}`}</dd></div>
            <div><dt>{t('issues.tokenUsage')}</dt><dd>{stats.tokens_in.toLocaleString(lang)} / {stats.tokens_out.toLocaleString(lang)}</dd></div>
            <div><dt>{t('issues.averageTokens')}</dt><dd>{Math.round(stats.avg_tokens_per_ticket).toLocaleString(lang)}</dd></div>
          </dl>
        </section>
      )}

      <div className={`issues-workspace${selected === null ? '' : ' issues-workspace-selected'}`}>
        <section ref={queue} className="project-card issues-queue" aria-labelledby="issues-queue-title">
          <header className="issues-panel-heading"><h2 id="issues-queue-title">{t('issues.listTitle')}</h2></header>
          {tickets.length === 0 ? (
            <p className="resource-empty">{t('project.noIssues')}</p>
          ) : (
            <ul className="issues-ticket-list">
              {tickets.map((ticket) => (
                <li className="issues-ticket-row" key={ticket.id}>
                  <button type="button" className="issues-ticket-open" data-issue-id={ticket.id} aria-pressed={ticket.id === selected?.ticket.id} disabled={interactionBusy} onClick={() => void openTicket(ticket.id)}>
                    <strong>{ticket.title}</strong>
                    <span className={`badge issue-state-${ticket.status}`}>{t(STATUS_KEYS[ticket.status] ?? 'issues.unavailable')}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {selected !== null && (
          <article className="project-card issues-ticket-detail">
            <button ref={backToQueue} type="button" className="btn btn-secondary issues-back-to-queue" disabled={interactionBusy} onClick={closeDetail}>{t('issues.backToQueue')}</button>
            <header className="issues-detail-heading">
              <div>
                <span className={`badge issue-state-${selected.ticket.status}`}>{t(STATUS_KEYS[selected.ticket.status] ?? 'issues.unavailable')}</span>
                <h2 ref={detailTitle} tabIndex={-1}>{selected.ticket.title}</h2>
                <p>{selected.ticket.description}</p>
                {selected.ticket.triage !== null && (
                  <div className="provider-card-meta">
                    {typeof selected.ticket.triage.category === 'string' && <span className="badge">{selected.ticket.triage.category}</span>}
                    {typeof selected.ticket.triage.severity === 'string' && <span className="badge">{t(SEVERITY_KEYS[selected.ticket.triage.severity] ?? 'issues.unavailable')}</span>}
                    {typeof selected.ticket.triage.summary === 'string' && <span>{selected.ticket.triage.summary}</span>}
                  </div>
                )}
              </div>
              <button type="button" className="btn btn-secondary issues-close-detail" disabled={interactionBusy} onClick={closeDetail} aria-label={t('issueWorkspace.closeIssue')}>×</button>
            </header>

            {selected.ticket.status === 'answered' && selected.ticket.answer !== null && (
              <section className="issues-answer">
                <header className="issues-panel-heading">
                  <h3>{t('issueWorkspace.suggestion')}</h3>
                  <button type="button" className="btn btn-secondary" disabled={!outcome.text} onClick={() => void copy('answer', outcome.text ?? '')}>{t('issueWorkspace.copySuggestion')}</button>
                </header>
                <div className="issues-answer-body" lang={outcome.displayLanguage}>{displayedOutcome}</div>
                {copyFeedback?.section === 'answer' && <p role="status" className="field-hint">{t(copyFeedback.success ? 'issueWorkspace.suggestionCopied' : 'issueWorkspace.suggestionCopyFailed')}</p>}
                {selected.ticket.citations.length > 0 && (
                  <div className="issues-citations">
                    <h4>{t('issues.sources')}</h4>
                    <ul>
                      {selected.ticket.citations.map((citation) => (
                        <li key={citation.source_ref}>
                          <CitationPath citation={citation} />
                          <span className="badge">{SOURCE_KEYS[citation.index_type] ? t(SOURCE_KEYS[citation.index_type]!) : citation.index_type}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
            )}

            {(selected.ticket.status === 'escalated' || selected.ticket.status === 'failed') && selected.ticket.escalate_reason !== null && (
              <section className="issues-escalation">
                <h3>{t(selected.ticket.status === 'failed' ? 'issues.statusFailed' : 'issues.escalateTitle')}</h3>
                <div className="issues-answer-body" lang={outcome.displayLanguage}>{displayedOutcome}</div>
                {selected.ticket.citations.length > 0 && (
                  <div className="issues-citations">
                    <h4>{t('issues.dossier')}</h4>
                    <ul>{selected.ticket.citations.map((citation) => <li key={citation.source_ref}><CitationPath citation={citation} /></li>)}</ul>
                  </div>
                )}
              </section>
            )}

            <TicketLogAttachments
              key={selected.ticket.id}
              ticketId={selected.ticket.id}
              api={api}
              disabled={busy !== null || intakeBusy || selected.ticket.status === 'running'}
              onUnreadyChange={updateLogBlocked}
              onBusyChange={setMutatingLogs}
            >
              {selected.ticket.status !== 'new' && selected.ticket.status !== 'running' && (
                <div className="issues-comment-field">
                  <label htmlFor="issue-rerun-comment">{t('issueWorkspace.rerunComment')}</label>
                  <textarea id="issue-rerun-comment" aria-describedby="issue-rerun-hint" maxLength={4000} rows={3} disabled={interactionBusy} value={rerunComment} onChange={(event) => setRerunComment(event.target.value)} />
                  <p id="issue-rerun-hint" className="field-hint">{t('issueWorkspace.rerunHint')}</p>
                </div>
              )}
            </TicketLogAttachments>
            <div className="issues-run-controls">
              {graph !== null && graph.profiles.length === 0 && (
                <div className="issues-profile-empty">
                  <p>{t('issueWorkspace.profileMissing')}</p>
                  {onOpenSolver && <button type="button" className="btn btn-secondary" disabled={interactionBusy} onClick={onOpenSolver}>{t('issueWorkspace.profileSetup')}</button>}
                </div>
              )}
              {graph !== null && graph.profiles.length > 0 && <div className="issues-profile-field">
                <label htmlFor="issue-profile">{t('issues.profile')}</label>
                <select id="issue-profile" aria-describedby="issue-profile-hint" disabled={interactionBusy} value={profileId ?? ''} onChange={(event) => setProfileId(event.target.value === '' ? null : Number(event.target.value))}>
                  <option value="" disabled>{t('issueWorkspace.profilePlaceholder')}</option>
                  {graph.profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
                </select>
                <p id="issue-profile-hint" className="field-hint">{t('issueWorkspace.profileHint')}</p>
              </div>}
              <button type="button" className="btn btn-primary" disabled={interactionBusy || !canRun(selected.ticket.id, selected.ticket.status)} onClick={() => { if (selectedProfile) void runTicket(selected.ticket.id, selectedProfile.id) }}>{busy === `run-${selected.ticket.id}` ? t('issues.running') : selected.ticket.status === 'new' ? t('issues.run') : t('issues.rerun')}</button>
            </div>

            <IssueRunStats detail={selected} />

            <section className="issues-trace" aria-labelledby="issue-trace-heading">
              <header className="issues-panel-heading">
                <h3 id="issue-trace-heading">{t('issues.trace')}</h3>
                <button type="button" className="btn btn-secondary" disabled={selected.steps.length === 0 && (selected.runs ?? []).length === 0} onClick={copyTrace}>{t('issueWorkspace.copyTrace')}</button>
              </header>
              {copyFeedback?.section === 'trace' && <p role="status" className="field-hint">{t(copyFeedback.success ? 'issueWorkspace.traceCopied' : 'issueWorkspace.traceCopyFailed')}</p>}
              <div ref={traceContent}>
                <h4>{t('issueWorkspace.runHistory')}</h4>
                {(selected.runs ?? []).map((run) => (
                  <section className="issues-run" key={run.id}>
                    <h5>{run.profile_name} · {STATUS_KEYS[run.status] ? t(STATUS_KEYS[run.status]!) : STEP_STATUS_KEYS[run.status] ? t(STEP_STATUS_KEYS[run.status]!) : run.status}</h5>
                    <p>{new Date(run.created_at).toLocaleString(lang)}</p>
                    {run.error && <p role="alert">{run.error}</p>}
                    <dl>{Object.entries(run.models).map(([role, model]) => <div key={role}><dt>{MODEL_ROLE_KEYS[role] ? t(MODEL_ROLE_KEYS[role]!) : role}</dt><dd>{model?.display_name ?? t('issues.unavailable')}</dd></div>)}</dl>
                    <TraceSteps steps={selected.steps.filter((step) => step.run_id === run.id)} models={run.models} />
                  </section>
                ))}
                {selected.steps.some((step) => step.run_id == null) && <section className="issues-run"><h5>{t('issues.historicalRun')}</h5><TraceSteps steps={selected.steps.filter((step) => step.run_id == null)} /></section>}
                {selected.steps.length === 0 && (selected.runs ?? []).length === 0 && <p className="resource-empty">{t('issues.unavailable')}</p>}
              </div>
            </section>
          </article>
        )}
      </div>
    </div>
  )
}

function CitationPath({ citation }: { citation: TicketCitation }) {
  const label = citation.label ? <strong>{citation.label} · </strong> : null
  if (citation.index_type === 'external_web' && /^https?:\/\/[^\s]+$/i.test(citation.path)) {
    return <>{label}<a href={citation.path} target="_blank" rel="noopener noreferrer">{citation.path}</a></>
  }
  return <>{label}<code>{citation.path}</code>{citation.start_line !== null && <span>:{citation.start_line}{citation.end_line && citation.end_line !== citation.start_line ? '–' + citation.end_line : ''}</span>}</>
}

function ReadableValue({ value, field }: { value: unknown; field?: string }) {
  const { t } = useT()
  if (value === null || value === undefined) return <span>—</span>
  if (value === 'disabled_by_profile') return <span>{t('issues.disabledByProfile')}</span>
  if (Array.isArray(value)) return <ul>{value.map((item, index) => <li key={index}><ReadableValue value={item} field={field} /></li>)}</ul>
  if (typeof value === 'object') return (
    <dl>{Object.entries(value).filter(([key]) => !/password|secret|token|credential|api.?key|authorization/i.test(key)).map(([key, item]) => (
      <div key={key}>
        <dt>{TRACE_FIELD_KEYS[key] ? t(TRACE_FIELD_KEYS[key]!) : key}</dt>
        <dd><ReadableValue value={item} field={key} /></dd>
      </div>
    ))}</dl>
  )
  if (typeof value === 'boolean') return <span>{t(value ? 'common.yes' : 'common.no')}</span>
  const translatedValue = field && typeof value === 'string' ? TRACE_VALUE_KEYS[field]?.[value] : undefined
  return <span>{translatedValue ? t(translatedValue) : String(value)}</span>
}

function TraceSteps({ steps, models }: { steps: TicketDetail['steps']; models?: NonNullable<TicketDetail['runs']>[number]['models'] }) {
  const { t } = useT()
  const count = (value: unknown): number | null => typeof value === 'number' ? value : Array.isArray(value) ? value.length : value && typeof value === 'object' ? Object.keys(value).length : null
  return <ol className="issues-step-list">{steps.map((step, index) => {
    const fragments = count(step.output_data.fragments)
    const refs = count(step.output_data.refs)
    const message = ['summary', 'finding', 'answer', 'escalate_reason', 'reason', 'error', 'category'].map((key) => step.output_data[key]).find((value) => typeof value === 'string') as string | undefined
    const reasonKey = message === undefined ? undefined : TRACE_VALUE_KEYS.reason?.[message]
    const summary = message === 'disabled_by_profile' ? t('issues.disabledByProfile') : reasonKey ? t(reasonKey) : message
    return <li key={index} className={`issues-step issues-step-${step.status ?? 'unknown'}`}>
    <div className="issues-step-heading"><strong>{STEP_KEYS[step.step] ? t(STEP_KEYS[step.step]!) : step.step.replaceAll('_', ' ')}</strong><span>{step.status && STEP_STATUS_KEYS[step.status] ? t(STEP_STATUS_KEYS[step.status]!) : t('issues.unavailable')}</span></div>
    <div className="issues-step-metrics">{t('issues.model')}: {Object.values(models ?? {}).find((model) => model?.id === step.model_id)?.display_name ?? step.model_id ?? t('issues.unavailable')}
    {step.status !== 'skipped' && <span> · {t('issues.duration', { value: String(step.duration_ms) })}</span>}
    <span> · {t('issues.tokenUsage')}: {step.tokens_in ?? '—'} / {step.tokens_out ?? '—'}</span>
    <span> · {t('issues.stepCost')}: {step.cost_usd === null ? '—' : `$${step.cost_usd.toFixed(6)}`}</span>
    </div>
    <p className="issues-step-summary">{[summary, fragments !== null ? t('issues.fragmentsCount', { count: String(fragments) }) : null, refs !== null ? t('issues.refsCount', { count: String(refs) }) : null].filter(Boolean).join(' · ') || (step.status === 'skipped' ? t('issues.stepSkipped') : t('issues.traceDetails'))}</p>
    <div className="issues-step-data"><h6>{t('issues.traceInput')}</h6><ReadableValue value={step.input_data} /></div>
    <div className="issues-step-data"><h6>{t('issues.traceOutput')}</h6><ReadableValue value={step.output_data} /></div>
  </li>})}</ol>
}
