import { useCallback, useEffect, useState } from 'react'
import { getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import type { TicketLogAttachment, TicketLogAttachmentStatus } from '../../../shared/api/types'
import { useT } from '../../../shared/i18n'
import type { TranslationKey } from '../../../shared/i18n'

interface Props {
  ticketId: number
  api: ApiClient
  onUnreadyChange: (ticketId: number, unready: boolean) => void
}

const POLL_INTERVAL_MS = 2000

const STATUS_KEYS: Record<TicketLogAttachmentStatus, TranslationKey> = {
  queued: 'issues.logStatusQueued',
  processing: 'issues.logStatusProcessing',
  ready: 'issues.logStatusReady',
  failed: 'issues.logStatusFailed',
}

export default function TicketLogAttachments({ ticketId, api, onUnreadyChange }: Props) {
  const { t } = useT()
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
    try {
      await api.uploadTicketLogAttachment(ticketId, file)
      refreshList()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusyId(null)
    }
  }

  const retry = async (attachmentId: number) => {
    setError(null)
    setBusyId(attachmentId)
    try {
      await api.retryTicketLogAttachment(ticketId, attachmentId)
      refreshList()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusyId(null)
    }
  }

  const remove = async (attachmentId: number) => {
    setError(null)
    setBusyId(attachmentId)
    try {
      await api.deleteTicketLogAttachment(ticketId, attachmentId)
      refreshList()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="issues-log-attachments" aria-labelledby="issues-log-title">
      <div className="project-card-heading">
        <div>
          <h3 id="issues-log-title">{t('issues.logAttachmentsTitle')}</h3>
          <p>{t('issues.logAttachmentsHint')}</p>
        </div>
      </div>

      <label className="issues-log-upload">
        {t('issues.attachLogs')}
        <input
          type="file"
          accept=".zip,.tar.gz,application/zip,application/gzip"
          disabled={busyId !== null}
          onChange={(event) => void upload(event)}
        />
      </label>
      <p className="field-hint">{t('issues.logArchiveHint')}</p>
      {error !== null && <div className="error" role="alert">{error}</div>}

      {attachments.length === 0 ? (
        <p className="resource-empty">{t('issues.logAttachmentsEmpty')}</p>
      ) : (
        <ul className="issues-log-list">
          {attachments.map((attachment) => (
            <li className="issues-log-row" key={attachment.id}>
              <div className="issues-log-info">
                <strong>{attachment.filename}</strong>
                <span>{formatSize(attachment.size_bytes)}</span>
                <span className={`badge issue-log-state-${attachment.status}`}>
                  {t(STATUS_KEYS[attachment.status])}
                </span>
                {attachment.error !== null && <span className="error">{attachment.error}</span>}
              </div>
              <div className="issues-log-actions">
                {attachment.status === 'failed' && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busyId !== null}
                    onClick={() => void retry(attachment.id)}
                  >
                    {t('issues.logRetry')}
                  </button>
                )}
                <button
                  type="button"
                  className="text-button"
                  disabled={busyId !== null}
                  aria-label={`${t('issues.logDelete')} ${attachment.filename}`}
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

function formatSize(sizeBytes: number): string {
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
}
