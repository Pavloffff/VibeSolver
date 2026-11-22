import { useEffect, useState } from 'react'
import { ApiClient, getApiClient, getErrorMessage } from '../../../shared/api/client'
import type { SolverProfileInput, SolverGraph, SolverProfile, WorkspaceModel } from '../../../shared/api/types'
import { useT, type TranslationKey } from '../../../shared/i18n'
import FlowDiagram, { useStepLabels } from './FlowDiagram'
import './solver.css'

type Props = { projectId: number; api?: ApiClient }
const inputFor = ({ name, enabled, models }: SolverProfile): SolverProfileInput => ({ name, enabled, models })

export default function SolverGraphPage({ projectId, api = getApiClient() }: Props) {
  return <ProjectGraph key={projectId} projectId={projectId} api={api} />
}

function ProjectGraph({ projectId, api }: Required<Props>) {
  const { t } = useT()
  const [graph, setGraph] = useState<SolverGraph | null>(null)
  const [models, setModels] = useState<WorkspaceModel[]>([])
  const [id, setId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    setError('')
    void Promise.all([api.getSolverGraph(projectId), api.listWorkspaceModels('chat')]).then(([data, choices]) => {
      if (active) {
        setGraph(data)
        setModels(choices.filter(model => ['available', 'installed'].includes(model.status)))
        setId(data.default_profile_id)
      }
    }).catch((reason: unknown) => { if (active) setError(getErrorMessage(reason)) })
    return () => { active = false }
  }, [projectId, api, attempt])
  const profile = graph?.profiles.find(p => p.id === id)
  return <section className="solver-page">
    <header><h1>{t('solver.title')}</h1><p>{t('solver.subtitle')}</p></header>
    {error && <div role="alert" className="error page-alert">{error} <button className="btn" onClick={() => setAttempt(n => n + 1)}>{t('solver.retry')}</button></div>}
    {graph && profile ? <ProfileEditor key={profile.id} graph={graph} profile={profile} choices={models} projectId={projectId} api={api}
      onChange={(next, selected) => { setGraph(next); setId(selected) }} onSelect={setId} />
      : !error && <p role="status">{t(graph ? 'solver.empty' : 'solver.loading')}</p>}
  </section>
}

type EditorProps = Required<Props> & { graph: SolverGraph; profile: SolverProfile; choices: WorkspaceModel[];
  onChange: (graph: SolverGraph, selected: number) => void; onSelect: (id: number) => void }

function ProfileEditor({ api, projectId, graph, profile, choices, onChange, onSelect }: EditorProps) {
  const { t } = useT()
  const steps = useStepLabels()
  const [draft, setDraft] = useState(() => inputFor(profile))
  const [creating, setCreating] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [step, setStep] = useState(graph.nodes[0]?.id ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState<TranslationKey | null>(null)
  const others = graph.profiles.filter(item => item.id !== profile.id)
  const [replacement, setReplacement] = useState(others[0]?.id)
  const isDefault = graph.default_profile_id === profile.id
  const dirty = creating || JSON.stringify(draft) !== JSON.stringify(inputFor(profile))
  const toggle = step === 'triage' || step === 'resolve' ? step : null
  const reset = () => { setDraft(inputFor(profile)); setCreating(false); setRenaming(false); setError(''); setNotice(null) }
  async function perform(operation: () => Promise<void>) {
    setBusy(true); setError(''); setNotice(null)
    try { await operation() } catch (reason) { setError(getErrorMessage(reason)) } finally { setBusy(false) }
  }
  function save() {
    void perform(async () => {
      const input = { ...draft, name: draft.name.trim() }
      const saved = creating ? await api.createSolverProfile(projectId, input) : await api.updateSolverProfile(projectId, profile.id, input)
      const profiles = creating ? [...graph.profiles, saved] : graph.profiles.map(item => item.id === saved.id ? saved : item)
      setDraft(inputFor(saved)); setCreating(false); setRenaming(false); setNotice('solver.saved')
      onChange({ ...graph, profiles }, saved.id)
    })
  }
  function modelSelect(role: keyof SolverProfileInput['models'], title: TranslationKey) {
    const value = draft.models[role]
    return <label>{t(title)}<select value={value ?? ''} onChange={event => setDraft({ ...draft, models: { ...draft.models, [role]: event.target.value ? Number(event.target.value) : null } })}>
      <option value="">{t(role === 'ticket_resolution' ? 'solver.choose' : 'solver.inherit')}</option>
      {value !== null && !choices.some(item => item.id === value) && <option value={value}>{t('solver.unavailable', { id: String(value) })}</option>}
      {choices.map(model => <option key={model.id} value={model.id}>{model.provider_name} · {model.display_name}</option>)}
    </select></label>
  }
  return <fieldset className="solver-workspace" disabled={busy}>
    <div className="solver-profilebar">
      <label>{t('solver.profile')}<select value={profile.id} disabled={dirty || removing} onChange={event => onSelect(Number(event.target.value))}>
        {graph.profiles.map(item => <option key={item.id} value={item.id}>{item.name}{item.id === graph.default_profile_id ? ' · ' + t('solver.active') : ''}</option>)}
      </select></label>
      <div className="solver-actions">
        <button className="btn" disabled={dirty || removing} onClick={() => { setDraft({ ...draft, name: t('solver.copy', { name: profile.name }) }); setCreating(true); setRenaming(true); setNotice(null) }}>{t('solver.newProfile')}</button>
        {!isDefault && <button className="btn" disabled={dirty || removing} onClick={() => void perform(async () => {
          await api.setDefaultSolverProfile(projectId, profile.id); onChange({ ...graph, default_profile_id: profile.id }, profile.id); setNotice('solver.defaultUpdated')
        })}>{t('solver.makeDefault')}</button>}
        <button className="btn" disabled={dirty || removing} onClick={() => { setRenaming(true); setNotice(null) }}>{t('solver.edit')}</button>
        <button className="btn" disabled={!others.length || dirty || removing} title={!others.length ? t('solver.last') : undefined} onClick={() => { setReplacement(others[0]?.id); setRemoving(true) }}>{t('solver.remove')}</button>
      </div>
    </div>
    {renaming && <label className="solver-name">{t('solver.profileName')}<input autoFocus maxLength={120} value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} /></label>}
    {removing && <div className="solver-confirm"><h3>{t('solver.confirmRemove', { name: profile.name })}</h3><p>{t('solver.removeHint')}</p>
      {isDefault && <label>{t('solver.replace')}<select value={replacement} onChange={event => setReplacement(Number(event.target.value))}>{others.map(other => <option key={other.id} value={other.id}>{other.name}</option>)}</select></label>}
      <div className="solver-actions"><button className="btn" onClick={() => setRemoving(false)}>{t('solver.cancel')}</button>
        <button className="btn" onClick={() => void perform(async () => {
          const next = isDefault ? replacement : graph.default_profile_id
          if (next === undefined) return
          await api.deleteSolverProfile(projectId, profile.id, isDefault ? next : undefined)
          onChange({ ...graph, profiles: others, default_profile_id: next }, next)
        })}>{t('solver.remove')}</button></div>
    </div>}
    <section className="solver-flow"><h2>{t('solver.flow')}</h2><FlowDiagram graph={graph} selected={step} enabled={draft.enabled} onSelect={setStep} /></section>
    <section className="solver-inspector"><div><small>{t('solver.inspect')}</small><h2>{steps.label(step)}</h2><p>{steps.description(step)}</p>
      {toggle && !draft.enabled[toggle] && <p>{t(toggle === 'triage' ? 'solver.triageOff' : 'solver.resolveOff')}</p>}</div>
      <div className="solver-controls">
        {toggle && <label className="solver-toggle"><input type="checkbox" checked={draft.enabled[toggle]} onChange={event => setDraft({ ...draft, enabled: { ...draft.enabled, [toggle]: event.target.checked } })} />{t('solver.toggle')}</label>}
        {step === 'triage' && draft.enabled.triage && <>{modelSelect('ticket_triage', 'solver.triageModel')}
          {!draft.enabled.resolve && draft.models.ticket_triage === null && modelSelect('ticket_resolution', 'solver.primary')}</>}
        {step === 'resolve' && draft.enabled.resolve && <>{modelSelect('ticket_resolution', 'solver.primary')}
          {draft.enabled.triage && <>{modelSelect('ticket_resolution_cheap', 'solver.light')}<p>{t('solver.lightHint')}</p></>}</>}
        {toggle && draft.enabled[toggle] && <p>{t('solver.providerHint')}</p>}
        {!toggle && graph.edges.some(edge => edge.source === step) && <div><small>{t('solver.next')}</small><p>{graph.edges.filter(edge => edge.source === step).map(edge => steps.label(edge.target)).join(' · ')}</p></div>}
      </div>
    </section>
    {error && <p role="alert" className="error">{error}</p>}
    <footer><span role="status">{dirty ? t('solver.pending') : notice && t(notice)}</span>
      {(dirty || renaming) && <button className="btn" onClick={reset}>{t('solver.cancel')}</button>}
      <button className="btn btn-primary" disabled={!dirty || !draft.name.trim() || removing} onClick={save}>{t('solver.save')}</button>
    </footer>
  </fieldset>
}
