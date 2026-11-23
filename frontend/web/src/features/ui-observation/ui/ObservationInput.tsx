import FilePicker from '../../../shared/ui/FilePicker'
import { useEffect, useState, type ChangeEvent } from 'react'
import { getErrorMessage, type ApiClient } from '../../../shared/api/client'
import type { UiObservation } from '../../../shared/api/types'
import { useT, type TranslationKey } from '../../../shared/i18n'

const ROLE_LABELS: Record<string, TranslationKey> = {
  button: 'issueWorkspace.roleButton', checkbox: 'issueWorkspace.roleCheckbox',
  combobox: 'issueWorkspace.roleCombobox', link: 'issueWorkspace.roleLink',
  radio: 'issueWorkspace.roleRadio', textbox: 'issueWorkspace.roleTextbox',
  img: 'issueWorkspace.roleImage', slider: 'issueWorkspace.roleSlider',
  generic: 'issueWorkspace.roleGeneric', switch: 'issueWorkspace.roleSwitch',
}

function readObservation(value: unknown): UiObservation | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const { role, name, width, height, visible, enabled, checked = null, observed_at } = value as Record<string, unknown>
  if (
    typeof role !== 'string' || typeof name !== 'string' ||
    typeof width !== 'number' || typeof height !== 'number' ||
    typeof visible !== 'boolean' || typeof enabled !== 'boolean' ||
    (typeof checked !== 'boolean' && checked !== null) || typeof observed_at !== 'string'
  ) return null
  return { role, name, width, height, visible, enabled, checked, observed_at }
}

export default function ObservationInput({ ticketId, api }: { ticketId: number; api: ApiClient }) {
  const { t, lang } = useT()
  const [observation, setObservation] = useState<UiObservation | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(true)
  const openHelper = window.vibesolver?.openUiObserver

  useEffect(() => {
    if (typeof api.getUiObservation !== 'function') return
    let active = true
    setBusy(true)
    void api.getUiObservation(ticketId)
      .then(value => { if (active) setObservation(value.observation) })
      .catch((reason: unknown) => { if (active) setError(getErrorMessage(reason)) })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [api, ticketId])

  if (typeof api.getUiObservation !== 'function') return null

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget
    const file = input.files?.[0]
    if (!file) return
    setBusy(true)
    setError('')
    try {
      if (file.size > 16384) throw new Error(t('issues.observationInvalid'))
      const data = readObservation(JSON.parse(await file.text()))
      if (!data) throw new Error(t('issues.observationInvalid'))
      const result = await api.setUiObservation(ticketId, data)
      setObservation(result.observation)
    } catch (reason) {
      setError(reason instanceof SyntaxError ? t('issues.observationInvalid') : getErrorMessage(reason))
    } finally {
      input.value = ''
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    setError('')
    try {
      await api.deleteUiObservation(ticketId)
      setObservation(null)
    } catch (reason) {
      setError(getErrorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  async function openDesktopHelper() {
    setError('')
    try {
      if (!(await openHelper?.(lang))?.ok) setError(t('issues.observationOpenError'))
    } catch {
      setError(t('issues.observationOpenError'))
    }
  }

  return <section className="issues-observation">
    <p className="field-hint">{t('issues.observationHint')}</p>
    {openHelper
      ? <button type="button" className="text-button" onClick={() => void openDesktopHelper()}>{t('issues.observationHelper')}</button>
      : <a href={`./ui-observer.html?lang=${lang}`} target="_blank" rel="noreferrer">{t('issues.observationHelper')}</a>}
    <div>
      <label htmlFor="ui-observation-upload">{t('issues.observationTitle')}</label>
      <FilePicker id="ui-observation-upload" accept=".json,application/json" disabled={busy} onChange={event => void upload(event)} />
    </div>
    {observation && <p>{ROLE_LABELS[observation.role] ? t(ROLE_LABELS[observation.role]!) : observation.role}: {observation.name} · {observation.width.toLocaleString(lang)} × {observation.height.toLocaleString(lang)}{' '}
      <button type="button" className="text-button" disabled={busy} onClick={() => void remove()}>{t('issues.observationDelete')}</button>
    </p>}
    {error && <p className="error" role="alert">{error}</p>}
  </section>
}
