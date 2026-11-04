import { useCallback, useEffect, useRef, useState } from 'react'
import { getApiClient, getErrorMessage } from '../api/client'
import type { ApiClient } from '../api/client'
import type { ImportStatus, Source } from '../api/types'
import { useT } from '../i18n'
import type { TranslationKey } from '../i18n'
import SourceForm from './SourceForm'

const STATUS_KEYS: Record<string, TranslationKey> = {
  pending: 'sources.statusPending',
  running: 'sources.statusRunning',
  done: 'sources.statusDone',
  failed: 'sources.statusFailed',
}

interface Props {
  api?: ApiClient
}

export default function SourcesPage({ api = getApiClient() }: Props) {
  const { t } = useT()
  const [sources, setSources] = useState<Source[]>([])
  const [imports, setImports] = useState<Record<number, ImportStatus>>({})
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const loadSources = useCallback(async () => {
    try {
      const list = await api.listSources()
      setSources(list)
      setError(null)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setLoaded(true)
    }
  }, [api])

  useEffect(() => {
    void loadSources()
    const timerMap = timers.current
    return () => {
      for (const timer of timerMap.values()) {
        clearTimeout(timer)
      }
      timerMap.clear()
    }
  }, [loadSources])

  const pollImport = useCallback(
    async (id: number) => {
      try {
        const status = await api.getImportStatus(id)
        setImports((prev) => ({ ...prev, [id]: status }))
        if (status.status === 'pending' || status.status === 'running') {
          const timer = setTimeout(() => {
            void pollImport(id)
          }, 2000)
          timers.current.set(id, timer)
        } else {
          timers.current.delete(id)
          void loadSources()
        }
      } catch (requestError) {
        setError(getErrorMessage(requestError))
      }
    },
    [api, loadSources],
  )

  const startImport = useCallback(
    async (id: number) => {
      try {
        await api.startImport(id)
        setImports((prev) => ({ ...prev, [id]: { status: 'pending', progress: 0, error: null } }))
        const timer = setTimeout(() => {
          void pollImport(id)
        }, 2000)
        timers.current.set(id, timer)
      } catch (requestError) {
        setError(getErrorMessage(requestError))
      }
    },
    [api, pollImport],
  )

  const removeSource = useCallback(
    async (id: number) => {
      if (!window.confirm(t('sources.confirmDelete'))) {
        return
      }
      try {
        await api.deleteSource(id)
        await loadSources()
      } catch (requestError) {
        setError(getErrorMessage(requestError))
      }
    },
    [api, loadSources, t],
  )

  const statusLabel = (status: string): string => {
    const key = STATUS_KEYS[status]
    return key !== undefined ? t(key) : status
  }

  return (
    <div>
      <div className="page-header">
        <h2>{t('common.sources')}</h2>
        <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
          {t('sources.add')}
        </button>
      </div>
      {error !== null && <p className="error">{error}</p>}
      {loaded && sources.length === 0 && <p>{t('sources.empty')}</p>}
      {sources.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>{t('sources.colName')}</th>
              <th>{t('sources.colType')}</th>
              <th>{t('sources.colImportStatus')}</th>
              <th>{t('sources.colEnabled')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => {
              const current = imports[source.id]
              const importing = current !== undefined && (current.status === 'pending' || current.status === 'running')
              return (
                <tr key={source.id}>
                  <td>{source.name}</td>
                  <td>{source.type}</td>
                  <td>
                    {current !== undefined ? (
                      <span>
                        <span className={`badge badge-${current.status}`}>{statusLabel(current.status)}</span>{' '}
                        {importing && <span className="progress">{current.progress}%</span>}
                        {current.error !== null && <span className="error">{current.error}</span>}
                      </span>
                    ) : source.last_import !== null ? (
                      <span className={`badge badge-${source.last_import.status}`}>
                        {statusLabel(source.last_import.status)}
                      </span>
                    ) : (
                      <span>—</span>
                    )}
                  </td>
                  <td>{source.enabled ? t('common.yes') : t('common.no')}</td>
                  <td>
                    <button
                      type="button"
                      className="btn"
                      disabled={importing}
                      onClick={() => {
                        void startImport(source.id)
                      }}
                    >
                      {t('sources.import')}
                    </button>{' '}
                    <button
                      type="button"
                      className="btn"
                      onClick={() => {
                        void removeSource(source.id)
                      }}
                    >
                      {t('sources.delete')}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {showForm && (
        <div className="modal-overlay">
          <div className="modal">
            <h2>{t('sources.add')}</h2>
            <SourceForm
              api={api}
              onCreated={() => {
                setShowForm(false)
                void loadSources()
              }}
              onClose={() => setShowForm(false)}
            />
          </div>
        </div>
      )}
    </div>
  )
}
