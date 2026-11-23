import FilePicker from '../../../shared/ui/FilePicker'
import { useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from 'react'
import { getErrorMessage, type ApiClient } from '../../../shared/api/client'
import { useT } from '../../../shared/i18n'
import { parseTicketText } from '../../../features/issues'

type IntakeMode = 'form' | 'txt' | 'zip'

interface Props {
  api: ApiClient
  projectId: number
  disabled: boolean
  onBusyChange: (busy: boolean) => void
  onCreated: (ticketId: number) => Promise<void>
}

export default function IssueIntake({ api, projectId, disabled, onBusyChange, onCreated }: Props) {
  const { t } = useT()
  const dialog = useRef<HTMLDialogElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const titleInput = useRef<HTMLInputElement>(null)
  const [mode, setMode] = useState<IntakeMode>('form')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [preview, setPreview] = useState<string | null>(null)
  const [logs, setLogs] = useState<File[]>([])
  const [createdId, setCreatedId] = useState<number | null>(null)
  const [busy, setBusy] = useState<'preview' | 'save' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pendingUpload = createdId !== null

  const openIntake = () => {
    dialog.current?.showModal()
    if (!pendingUpload && busy === null) titleInput.current?.focus()
  }

  const closeIntake = () => {
    dialog.current?.close()
    trigger.current?.focus()
  }

  const trapTab = (event: KeyboardEvent<HTMLDialogElement>) => {
    if (event.key !== 'Tab') return
    const controls = event.currentTarget.querySelectorAll<HTMLElement>(
      'button:enabled, input:enabled, select:enabled, textarea:enabled',
    )
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (first === undefined || last === undefined) {
      event.preventDefault()
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  const importText = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0]
    event.currentTarget.value = ''
    if (file === undefined) return
    setError(null)
    const extension = mode === 'zip' ? '.zip' : '.txt'
    if (!file.name.toLowerCase().endsWith(extension)) {
      setError(t(mode === 'zip' ? 'issueWorkspace.zipInvalid' : 'issues.importTextInvalidType'))
      return
    }

    setBusy('preview')
    try {
      const text = mode === 'zip' ? (await api.previewTicketArchive(file)).text : await file.text()
      const parsed = parseTicketText(text)
      if (parsed === null || parsed.title.length < 3 || parsed.title.length > 200 || parsed.description.length < 10 || parsed.description.length > 20000) {
        setError(t('issues.importTextInvalidContent'))
        return
      }
      setTitle(parsed.title)
      setDescription(parsed.description)
      setPreview(file.name)
    } catch (requestError) {
      setError(mode === 'zip' ? getErrorMessage(requestError) : t('issues.importTextReadError'))
    } finally {
      setBusy(null)
    }
  }

  const selectLogs = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.currentTarget.files ?? [])
    event.currentTarget.value = ''
    if (files.length === 0) return
    if (files.some(({ name }) => !/\.(zip|tar\.gz)$/i.test(name))) {
      setError(t('issues.logInvalidType'))
      return
    }
    setError(null)
    setLogs(files)
  }

  const finish = async (ticketId: number) => {
    setCreatedId(null)
    setMode('form')
    setTitle('')
    setDescription('')
    setPreview(null)
    setLogs([])
    setError(null)
    await onCreated(ticketId)
    closeIntake()
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (busy !== null || disabled) return
    setBusy('save')
    onBusyChange(true)
    setError(null)
    try {
      const ticketId = createdId ?? (await api.createTicket(projectId, title, description)).id
      setCreatedId(ticketId)
      for (const file of logs) {
        await api.uploadTicketLogAttachment(ticketId, file)
        setLogs((remaining) => remaining.filter((item) => item !== file))
      }
      await finish(ticketId)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy(null)
      onBusyChange(false)
    }
  }

  const skipRemaining = async () => {
    if (createdId === null) return
    setBusy('save')
    onBusyChange(true)
    try {
      await finish(createdId)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy(null)
      onBusyChange(false)
    }
  }

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="btn btn-primary issues-intake-open"
        aria-haspopup="dialog"
        aria-controls="issue-intake"
        disabled={disabled}
        onClick={openIntake}
      >
        <span aria-hidden="true">+</span> {t('project.addIssue')}
      </button>
      <dialog
        ref={dialog}
        id="issue-intake"
        className="issues-intake-dialog"
        aria-labelledby="issue-intake-title"
        onCancel={(event) => {
          event.preventDefault()
          if (busy !== 'save') closeIntake()
        }}
        onKeyDown={trapTab}
      >
        <div className="issues-intake-heading">
          <h2 id="issue-intake-title">{t('project.addIssue')}</h2>
          <button type="button" className="btn btn-secondary issues-intake-close" disabled={busy === 'save'} onClick={closeIntake} aria-label={t('issueWorkspace.closeIntake')}>×</button>
        </div>
        <form className="issues-create-form" onSubmit={(event) => void save(event)}>
          <fieldset disabled={disabled || busy !== null || pendingUpload}>
            <label htmlFor="issue-intake-mode">{t('issueWorkspace.intakeMode')}</label>
            <select id="issue-intake-mode" value={mode} onChange={(event) => {
              setMode(event.target.value as IntakeMode)
              setPreview(null)
              setError(null)
            }}>
              <option value="form">{t('issueWorkspace.intakeForm')}</option>
              <option value="txt">{t('issueWorkspace.intakeTxt')}</option>
              <option value="zip">{t('issueWorkspace.intakeZip')}</option>
            </select>
            {mode !== 'form' && (
              <div className="issues-file-field">
                <label htmlFor="issue-source-file">{t(mode === 'zip' ? 'issueWorkspace.importZip' : 'issues.importTextFile')}</label>
                <FilePicker id="issue-source-file" key={mode} accept={mode === 'zip' ? '.zip,application/zip' : '.txt,text/plain'} aria-describedby="issue-source-hint" onChange={(event) => void importText(event)} />
                <p id="issue-source-hint" className="field-hint">{t(mode === 'zip' ? 'issueWorkspace.zipHint' : 'issues.importTextHint')}</p>
                {preview !== null && <p role="status" className="issues-file-preview"><strong>{preview}</strong> · {t('issueWorkspace.previewHint')}</p>}
              </div>
            )}
            <label htmlFor="issue-intake-title-input">{t('issues.titleLabel')}</label>
            <input ref={titleInput} id="issue-intake-title-input" required minLength={3} maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} />
            <label htmlFor="issue-intake-description">{t('issues.descriptionLabel')}</label>
            <textarea id="issue-intake-description" required minLength={10} maxLength={20000} rows={8} value={description} onChange={(event) => setDescription(event.target.value)} />
            <div className="issues-file-field">
              <label htmlFor="issue-intake-logs">{t('issueWorkspace.intakeLogs')}</label>
              <FilePicker id="issue-intake-logs" multiple accept=".zip,.tar.gz,application/zip,application/gzip" aria-describedby="issue-logs-hint" onChange={selectLogs} />
              <p id="issue-logs-hint" className="field-hint">{t('issueWorkspace.intakeLogsHint')}</p>
            </div>
            {!pendingUpload && logs.length > 0 && <button type="button" className="text-button issues-clear-archives" onClick={() => setLogs([])}>{t('issueWorkspace.clearArchives')}</button>}
          </fieldset>
          {logs.length > 0 && <ul className="issues-intake-files">{logs.map((file, index) => <li key={index}>{file.name}</li>)}</ul>}
          {error !== null && <div className="error issue-inline-error" role="alert">{pendingUpload && <p>{t('issueWorkspace.partialUpload', { id: String(createdId) })}</p>}{error}</div>}
          <div className="issues-form-actions">
            <button type="submit" className="btn btn-primary" disabled={disabled || busy !== null}>
              {busy === 'save' ? t('project.uploading') : pendingUpload ? t('issueWorkspace.retryUpload') : t('project.addIssue')}
            </button>
            {pendingUpload && <button type="button" className="text-button" disabled={disabled || busy !== null} onClick={() => void skipRemaining()}>{t('issueWorkspace.skipRemaining')}</button>}
          </div>
        </form>
      </dialog>
    </>
  )
}
