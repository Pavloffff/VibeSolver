import { useEffect, useId, useRef, useState, useSyncExternalStore } from 'react'
import { ApiClient, getErrorMessage } from '../../../shared/api/client'
import type { DiagnosticTools, SolverProfileInput, SolverGraph, SolverProfile, WorkspaceModel } from '../../../shared/api/types'
import { getApiBaseUrl } from '../../../shared/config'
import { useT, type TranslationKey } from '../../../shared/i18n'
import { getApplyQueues, type DiagnosticInput } from './autoApply'
import FlowDiagram, { useStepLabels } from './FlowDiagram'
import './solver.css'

type Props = { projectId: number; api?: ApiClient }
type Queues = ReturnType<typeof getApplyQueues>
const inputFor = ({ name, enabled, models }: SolverProfile): SolverProfileInput => ({ name, enabled, models })
const inputForTools = ({ ui_probe, web_provider, allow_web_search }: DiagnosticTools): DiagnosticInput => ({ ui_probe, web_provider, allow_web_search: allow_web_search ?? false })
const blankProfile = (): SolverProfileInput => ({
  name: '', enabled: { triage: true, resolve: true },
  models: { ticket_resolution: null, ticket_triage: null, ticket_resolution_cheap: null },
})
const needsModel = ({ enabled, models }: SolverProfileInput) => (enabled.resolve || (enabled.triage && !models.ticket_triage)) && !models.ticket_resolution
const sameInput = (left: SolverProfileInput, right: SolverProfileInput) => JSON.stringify(left) === JSON.stringify(right)
const clientsByServer = new Map<string, ApiClient>()

export default function SolverGraphPage({ projectId, api }: Props) {
  if (api) return <ProjectGraph key={projectId} projectId={projectId} api={api} />
  const server = getApiBaseUrl()
  let client = clientsByServer.get(server)
  if (!client) {
    client = new ApiClient(() => server)
    clientsByServer.set(server, client)
  }
  return <ProjectGraph key={`${server}:${projectId}`} projectId={projectId} api={client} />
}

function ProjectGraph({ projectId, api }: Required<Props>) {
  const { t } = useT()
  const queues = getApplyQueues(api, projectId)
  const [graph, setGraph] = useState<SolverGraph | null>(null)
  const [models, setModels] = useState<WorkspaceModel[]>([])
  const [id, setId] = useState<number | null>(null)
  const [creating, setCreating] = useState<SolverProfileInput | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [tools, setTools] = useState<DiagnosticTools | null>(null)
  const webProviderHintId = useId()
  const creation = useSyncExternalStore(queues.create.subscribe, queues.create.getSnapshot)
  const toolWrite = useSyncExternalStore(queues.tools.subscribe, queues.tools.getSnapshot)
  const lastCreation = useRef(creation)
  const lastToolsWrite = useRef(toolWrite)

  useEffect(() => {
    let active = true
    setError('')
    void queues.wait().then(() => Promise.all([api.getSolverGraph(projectId), api.listWorkspaceModels('chat')])).then(([data, choices]) => {
      if (!active) return
      setGraph(data)
      setModels(choices.filter(model => ['available', 'installed'].includes(model.status)))
      const outcome = queues.create.getSnapshot()
      const newProfileId = outcome.status === 'saved' && outcome.result.id !== queues.seenCreationId ? outcome.result.id : null
      const preferredId = newProfileId ?? queues.selectedProfileId
      const preferred = data.profiles.find(profile => profile.id === preferredId)
      const selected = preferred?.id ?? data.profiles[0]?.id ?? null
      queues.selectedProfileId = selected
      if (newProfileId !== null) queues.seenCreationId = newProfileId
      setId(selected)
      if (outcome.status === 'failed') setCreating(outcome.input)
    }).catch((reason: unknown) => { if (active) setError(getErrorMessage(reason)) })
    return () => { active = false }
  }, [projectId, api, queues, attempt])

  useEffect(() => {
    if (typeof api.getDiagnosticTools !== 'function') return
    let active = true
    void queues.tools.wait().then(() => api.getDiagnosticTools(projectId)).then(value => { if (active) setTools(value) })
      .catch((reason: unknown) => { if (active) setError(getErrorMessage(reason)) })
    return () => { active = false }
  }, [api, projectId, queues, attempt])

  useEffect(() => {
    if (lastCreation.current === creation) return
    lastCreation.current = creation
    if (creation.status !== 'saved') return
    setGraph(current => current === null || current.profiles.some(profile => profile.id === creation.result.id)
      ? current : { ...current, profiles: [...current.profiles, creation.result] })
    queues.selectedProfileId = creation.result.id
    queues.seenCreationId = creation.result.id
    setId(creation.result.id)
    setCreating(null)
  }, [creation, queues])

  useEffect(() => {
    if (lastToolsWrite.current === toolWrite) return
    lastToolsWrite.current = toolWrite
    if (toolWrite.status === 'saved') setTools(toolWrite.result)
  }, [toolWrite])

  const profile = graph?.profiles.find(value => value.id === id)
  const toolDraft = tools === null ? null : toolWrite.status === 'saving' || toolWrite.status === 'failed'
    ? { ...tools, ...toolWrite.input } : tools
  const selectedWebProvider = toolDraft?.web_provider ?? null
  const hasWebProvider = selectedWebProvider !== null && toolDraft?.available_web_providers.includes(selectedWebProvider) === true
  const updateTools = (patch: Partial<DiagnosticInput>) => {
    if (toolDraft === null) return
    const queued = queues.tools.getSnapshot()
    const input = queued.status === 'saving' || queued.status === 'failed' ? queued.input : inputForTools(toolDraft)
    const next = { ...input, ...patch }
    if (next.web_provider === null || !toolDraft.available_web_providers.includes(next.web_provider)) {
      next.web_provider = null
      next.allow_web_search = false
    }
    queues.tools.submit(next)
  }
  const selectProfile = (next: number | null) => {
    queues.selectedProfileId = next
    setId(next)
  }

  function startProfile(source?: SolverProfile) {
    queues.create.reset()
    if (!source || !graph) {
      setCreating(blankProfile())
      return
    }
    const base = t('solver.copy', { name: source.name })
    const names = new Set(graph.profiles.map(existing => existing.name))
    let name = base.slice(0, 120)
    let suffix = 2
    while (names.has(name)) {
      const ending = ` (${suffix++})`
      name = base.slice(0, 120 - ending.length) + ending
    }
    setCreating({ ...inputFor(source), name })
  }

  return <section className="solver-page">
    <header><h1>{t('solver.title')}</h1><p>{t('solver.subtitle')}</p></header>
    {error && <div role="alert" className="error page-alert">{error} <button type="button" className="btn" onClick={() => setAttempt(n => n + 1)}>{t('solver.retry')}</button></div>}
    {graph && (profile || creating) && <ProfileEditor
      key={creating ? 'new' : profile?.id}
      graph={graph} profile={creating ? undefined : profile} initial={creating ?? undefined}
      choices={models} projectId={projectId} api={api} queues={queues}
      onApplied={saved => setGraph(current => current && { ...current, profiles: current.profiles.map(item => item.id === saved.id ? saved : item) })}
      onRemoved={removed => {
        const profiles = graph.profiles.filter(item => item.id !== removed)
        setGraph(current => current && { ...current, profiles })
        selectProfile(profiles[0]?.id ?? null)
      }}
      onSelect={selectProfile} onClone={startProfile} onCancel={() => { queues.create.reset(); setCreating(null) }}
    />}
    {graph && !profile && !creating && <section className="solver-tools"><h2>{t('solver.empty')}</h2><p>{t('solver.firstProfileHint')}</p>
      <button type="button" className="btn btn-primary" onClick={() => startProfile()}>{t('solver.createProfile')}</button>
    </section>}
    {!graph && !error && <p role="status">{t('solver.loading')}</p>}
    {toolDraft && <section className="solver-tools"><h2>{t('solver.tools')}</h2><p>{t('solver.toolsHint')}</p>
      <label>{t('solver.uiProbe')}<select value={toolDraft.ui_probe ?? ''} onChange={event => updateTools({ ui_probe: event.target.value || null })}><option value="">{t('solver.disabled')}</option>{toolDraft.available_ui_probes.map(alias => <option key={alias} value={alias}>{alias}</option>)}</select></label>
      <label>{t('solver.webProvider')}<select value={selectedWebProvider ?? ''} onChange={event => updateTools({ web_provider: event.target.value || null })}>
        <option value="">{t('solver.disabled')}</option>
        {selectedWebProvider !== null && !hasWebProvider && <option value={selectedWebProvider} disabled>{t('solver.unavailableWebProvider', { name: selectedWebProvider })}</option>}
        {toolDraft.available_web_providers.map(alias => <option key={alias} value={alias}>{alias}</option>)}
      </select></label>
      <label className="solver-toggle"><input type="checkbox" checked={toolDraft.allow_web_search ?? false} disabled={!hasWebProvider && !toolDraft.allow_web_search} aria-describedby={!hasWebProvider ? webProviderHintId : undefined} onChange={event => updateTools({ allow_web_search: event.target.checked })} />{t('issues.diagnosticWebSearch')}</label>
      {!hasWebProvider && <p id={webProviderHintId}>{t('solver.selectWebProviderHint')}</p>}
      <p>{t('solver.webConsentHint')}</p>
      <ApplyStatus state={toolWrite} retry={queues.tools.retry} />
    </section>}
  </section>
}

function ApplyStatus({ state, retry }: { state: { status: 'idle' | 'saving' | 'saved' } | { status: 'failed'; error: unknown }; retry: () => void }) {
  const { t } = useT()
  if (state.status === 'failed') {
    return <div role="alert" className="solver-apply-status error">{t('solver.applyFailed')} {getErrorMessage(state.error)} <button type="button" className="btn" onClick={retry}>{t('solver.retry')}</button></div>
  }
  return <div className="solver-apply-status" role="status">{state.status === 'saving' ? t('solver.applying') : state.status === 'saved' ? t('solver.applied') : ''}</div>
}

type EditorProps = Required<Props> & {
  graph: SolverGraph; profile?: SolverProfile; initial?: SolverProfileInput; choices: WorkspaceModel[]; queues: Queues;
  onApplied: (profile: SolverProfile) => void; onRemoved: (id: number) => void; onSelect: (id: number) => void;
  onClone: (profile: SolverProfile) => void; onCancel: () => void;
}

function ProfileEditor({ api, projectId, graph, profile, initial, choices, queues, onApplied, onRemoved, onSelect, onClone, onCancel }: EditorProps) {
  const { t } = useT()
  const steps = useStepLabels()
  const queue = profile ? queues.profile(profile.id) : queues.create
  const write = useSyncExternalStore(queue.subscribe, queue.getSnapshot)
  const lastWrite = useRef(write)
  const [draft, setDraft] = useState(() => write.status === 'failed' || write.status === 'saving'
    ? write.input : profile ? inputFor(profile) : initial ?? blankProfile())
  const [name, setName] = useState(draft.name)
  const [removing, setRemoving] = useState(false)
  const [renaming, setRenaming] = useState(!profile)
  const [step, setStep] = useState(!profile ? 'resolve' : graph.nodes[0]?.id ?? '')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const lacksModel = (value: SolverProfileInput) => needsModel(value) || (!profile && Object.values(value.models)
    .some(id => id !== null && !choices.some(choice => choice.id === id)))
  const invalidModel = lacksModel(draft)
  const incompleteDraft = invalidModel && (!profile || !sameInput(draft, inputFor(profile)))
  const toggle = graph.nodes.find(node => node.id === step)?.optional ? step as keyof SolverProfileInput['enabled'] : null
  const busy = deleting || write.status === 'saving'
  const cannotLeave = busy || removing || incompleteDraft || write.status === 'failed' || (renaming && name.trim() !== draft.name)

  useEffect(() => {
    if (lastWrite.current === write) return
    lastWrite.current = write
    if (profile && write.status === 'saved') onApplied(write.result)
  }, [onApplied, profile, write])

  function apply(next: SolverProfileInput) {
    const current = queue.getSnapshot()
    if (removing || (!profile && current.status === 'saving')) return
    setDraft(next)
    if (!next.name || lacksModel(next)) return
    if (current.status !== 'idle' && sameInput(next, current.input)) return
    if (current.status === 'idle' && profile && sameInput(next, inputFor(profile))) return
    queue.submit(next)
  }

  function applyName() {
    const committed = name.trim()
    if (!committed || (!profile && busy)) return
    setName(committed)
    if (profile) setRenaming(false)
    apply({ ...draft, name: committed })
  }

  function updateDraft(next: SolverProfileInput) {
    apply(profile ? next : { ...next, name: name.trim() })
  }

  function reset() {
    if (!profile) return onCancel()
    queue.reset()
    const saved = inputFor(profile)
    setDraft(saved)
    setName(saved.name)
    setRenaming(false)
  }

  async function remove() {
    if (!profile || busy) return
    setDeleting(true)
    setDeleteError('')
    try {
      await api.deleteSolverProfile(projectId, profile.id)
      onRemoved(profile.id)
    } catch (reason) {
      setDeleteError(getErrorMessage(reason))
    } finally {
      setDeleting(false)
    }
  }

  function modelSelect(role: keyof SolverProfileInput['models'], title: TranslationKey) {
    const value = draft.models[role]
    return <label>{t(title)}<select aria-label={t(title)} value={value ?? ''} disabled={removing} onChange={event => updateDraft({ ...draft, models: { ...draft.models, [role]: event.target.value ? Number(event.target.value) : null } })}>
      <option value="">{t(role === 'ticket_resolution' ? 'solver.choose' : 'solver.inherit')}</option>
      {value !== null && !choices.some(item => item.id === value) && <option value={value}>{t('solver.unavailable', { id: String(value) })}</option>}
      {choices.map(model => <option key={model.id} value={model.id}>{model.provider_name} · {model.display_name}</option>)}
    </select></label>
  }

  return <>
    <fieldset className="solver-workspace" disabled={deleting || (!profile && write.status === 'saving')}>
      {profile && <div className="solver-profilebar">
        <label>{t('solver.profile')}<select value={profile.id} disabled={cannotLeave} onChange={event => onSelect(Number(event.target.value))}>
          {graph.profiles.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        <div className="solver-actions">
          <button type="button" className="btn" disabled={cannotLeave} onClick={() => onClone(profile)}>{t('solver.newProfile')}</button>
          <button type="button" className="btn" disabled={removing || renaming} onClick={() => setRenaming(true)}>{t('solver.edit')}</button>
          <button type="button" className="btn" disabled={cannotLeave} onClick={() => setRemoving(true)}>{t('solver.remove')}</button>
        </div>
      </div>}
      {renaming && <label className="solver-name">{t('solver.profileName')}<input autoFocus maxLength={120} value={name} onChange={event => setName(event.target.value)} onBlur={applyName} onKeyDown={event => {
        if (event.key === 'Enter') { event.preventDefault(); event.currentTarget.blur() }
      }} /></label>}
      {removing && profile && <div className="solver-confirm"><h3>{t('solver.confirmRemove', { name: profile.name })}</h3><p>{t('solver.removeHint')}</p>
        <div className="solver-actions"><button type="button" className="btn" onClick={() => setRemoving(false)}>{t('solver.cancel')}</button>
          <button type="button" className="btn" onClick={() => void remove()}>{t('solver.remove')}</button></div>
        {deleteError && <p role="alert" className="error">{deleteError}</p>}
      </div>}
      <section className="solver-flow"><h2>{t('solver.flow')}</h2><FlowDiagram graph={graph} selected={step} enabled={draft.enabled} onSelect={setStep} /></section>
      <section className="solver-inspector"><div><small>{t('solver.inspect')}</small><h2>{steps.label(step)}</h2><p>{steps.description(step)}</p>
        {toggle && !draft.enabled[toggle] && <p>{t(toggle === 'triage' ? 'solver.triageOff' : toggle === 'resolve' ? 'solver.resolveOff' : 'solver.specialistOff')}</p>}</div>
        <div className="solver-controls">
          {toggle && <label className="solver-toggle"><input type="checkbox" checked={draft.enabled[toggle] ?? false} disabled={removing} onChange={event => updateDraft({ ...draft, enabled: { ...draft.enabled, [toggle]: event.target.checked } })} />{t('solver.toggle')}</label>}
          {step === 'triage' && draft.enabled.triage && <>{modelSelect('ticket_triage', 'solver.triageModel')}
            {!draft.enabled.resolve && draft.models.ticket_triage === null && modelSelect('ticket_resolution', 'solver.primary')}</>}
          {step === 'resolve' && draft.enabled.resolve && <>{modelSelect('ticket_resolution', 'solver.primary')}
            {draft.enabled.triage && <>{modelSelect('ticket_resolution_cheap', 'solver.light')}<p>{t('solver.lightHint')}</p></>}</>}
          {toggle && draft.enabled[toggle] && <p>{t('solver.providerHint')}</p>}
          {toggle && ['flow', 'logs', 'code'].includes(toggle) && <p>{t('solver.specialistModelHint')}</p>}
          {!toggle && graph.edges.some(edge => edge.source === step) && <div><small>{t('solver.next')}</small><p>{graph.edges.filter(edge => edge.source === step).map(edge => steps.label(edge.target)).join(' · ')}</p></div>}
        </div>
      </section>
      <footer>
        {(renaming && !name.trim()) ? <span role="status">{t('solver.enterName')}</span> : invalidModel && <span role="status">{t('solver.chooseModelHint')}</span>}
        {(!profile || renaming || incompleteDraft || write.status === 'failed') && <button type="button" className="btn" disabled={busy} onMouseDown={event => event.preventDefault()} onClick={reset}>{t('solver.cancel')}</button>}
      </footer>
    </fieldset>
    <ApplyStatus state={write} retry={queue.retry} />
  </>
}
