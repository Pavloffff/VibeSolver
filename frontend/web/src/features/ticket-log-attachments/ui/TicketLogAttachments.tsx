import FilePicker from '../../../shared/ui/FilePicker'
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import type { TicketLogAttachment, TicketLogAttachmentStatus } from '../../../shared/api/types'
import { useT } from '../../../shared/i18n'
import type { TranslationKey } from '../../../shared/i18n'

interface Props {
  ticketId: number
  api: ApiClient
  disabled?: boolean
  children?: ReactNode
  onBusyChange?: (busy: boolean) => void
  onUnreadyChange: (ticketId: number, unready: boolean) => void
}

const POLL_INTERVAL_MS = 2000

const STATUS_KEYS: Record<TicketLogAttachmentStatus, TranslationKey> = {
  queued: 'issues.logStatusQueued',
  processing: 'issues.logStatusProcessing',
  ready: 'issues.logStatusReady',
  failed: 'issues.logStatusFailed',
}

export default function TicketLogAttachments({ ticketId, api, disabled = false, children, onBusyChange, onUnreadyChange }: Props) {
  const { t, lang } = useT()
  const hasAdditionalEvidence = children !== undefined && children !== null && children !== false
  const [attachments, setAttachments] = useState<TicketLogAttachment[]>([])
  const [busyId, setBusyId] = useState<number | 'upload' | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    let timer: number | undefined

    const refresh = async () => {
      try {
        const items = await api.listTicketLogAttachments(ticketId)
        if (!active) return
        setAttachments(items)
        const unready = items.some((item) => item.status !== 'ready')
        onUnreadyChange(ticketId, unready)
        if (items.some((item) => item.status === 'queued' || item.status === 'processing')) {
          timer = window.setTimeout(() => void refresh(), POLL_INTERVAL_MS)
        }
      } catch (requestError) {
        if (!active) return
        setError(getErrorMessage(requestError))
      }
    }

    void refresh()
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [api, onUnreadyChange, refreshKey, ticketId])

  const refreshList = useCallback(() => setRefreshKey((current) => current + 1), [])

  const upload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget
    const file = input.files?.[0]
    if (file === undefined) return
    input.value = ''
    setError(null)
    const filename = file.name.toLowerCase()
    if (!filename.endsWith('.zip') && !filename.endsWith('.tar.gz')) {
      setError(t('issues.logInvalidType'))
      return
    }
    setBusyId('upload')
    onBusyChange?.(true)
    try {
      const attachment = await api.uploadTicketLogAttachment(ticketId, file)
      if (attachment.status !== 'ready') onUnreadyChange(ticketId, true)
      refreshList()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusyId(null)
      onBusyChange?.(false)
    }
  }

  const retry = async (attachmentId: number) => {
    setError(null)
    setBusyId(attachmentId)
    onBusyChange?.(true)
    try {
      await api.retryTicketLogAttachment(ticketId, attachmentId)
      refreshList()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusyId(null)
      onBusyChange?.(false)
    }
  }

  const remove = async (attachmentId: number) => {
    setError(null)
    setBusyId(attachmentId)
    onBusyChange?.(true)
    try {
      await api.deleteTicketLogAttachment(ticketId, attachmentId)
      refreshList()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusyId(null)
      onBusyChange?.(false)
    }
  }

  return (
    <section className="issues-log-attachments" aria-labelledby="issues-log-title">
      <div className="project-card-heading">
        <div>
          <h3 id="issues-log-title">{t(hasAdditionalEvidence ? 'issueWorkspace.rerunEvidence' : 'issues.logAttachmentsTitle')}</h3>
          {!hasAdditionalEvidence && <p>{t('issues.logAttachmentsHint')}</p>}
        </div>
      </div>

      <div className="issues-log-evidence">
        {children}
        <div className="issues-log-picker">
          <label htmlFor="issue-log-upload" className="issues-log-upload">{t('issues.attachLogs')}</label>
          <FilePicker
            id="issue-log-upload"
            aria-describedby="issue-log-upload-hint"
            accept=".zip,.tar.gz,application/zip,application/gzip"
            disabled={disabled || busyId !== null}
            onChange={(event) => void upload(event)}
          />
          <p id="issue-log-upload-hint" className="field-hint">{t('issues.logArchiveHint')}</p>
        </div>
      </div>
      {error !== null && <div className="error" role="alert">{error}</div>}

      {attachments.length === 0 ? (
        <p className="resource-empty">{t('issues.logAttachmentsEmpty')}</p>
      ) : (
        <ul className="issues-log-list">
          {attachments.map((attachment) => (
            <li className="issues-log-row" key={attachment.id}>
              <div className="issues-log-info">
                <strong>{attachment.filename}</strong>
                <span>{t(attachment.size_bytes < 1024 ** 2 ? 'issueWorkspace.logSizeKiB' : 'issueWorkspace.logSizeMiB', {
                  size: (attachment.size_bytes / (attachment.size_bytes < 1024 ** 2 ? 1024 : 1024 ** 2)).toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
                })}</span>
                <span className={`badge issue-log-state-${attachment.status}`}>
                  {t(STATUS_KEYS[attachment.status] ?? 'issues.unavailable')}
                </span>
                {attachment.error !== null && <span className="error">{attachment.error.startsWith('Не удалось поставить архив в очередь')
                  ? t('issueWorkspace.logQueueError')
                  : attachment.error.startsWith('Не удалось проиндексировать архив логов')
                    ? t('issueWorkspace.logIndexError')
                    : attachment.error}</span>}
              </div>
              <div className="issues-log-actions">
                {attachment.status === 'failed' && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={disabled || busyId !== null}
                    onClick={() => void retry(attachment.id)}
                  >
                    {t('issues.logRetry')}
                  </button>
                )}
                <button
                  type="button"
                  className="text-button"
                  disabled={disabled || busyId !== null}
                  aria-label={t('issueWorkspace.removeLog', { filename: attachment.filename })}
                  onClick={() => void remove(attachment.id)}
                >
                  {t('issues.logDelete')}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
