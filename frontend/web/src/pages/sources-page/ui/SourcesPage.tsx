import { useCallback, useEffect, useState } from 'react'
import { getApiClient, getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import { SourceStatusBadge } from '../../../entities/source'
import type { Source } from '../../../entities/source'
import { useT } from '../../../shared/i18n'
import SourceForm from '../../../features/add-source'
import { useImportRunner } from '../../../features/run-import'

interface Props {
  api?: ApiClient
}

export default function SourcesPage({ api = getApiClient() }: Props) {
  const { t } = useT()
  const [sources, setSources] = useState<Source[]>([])
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [loaded, setLoaded] = useState(false)

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
  }, [loadSources])

  const reportError = useCallback(
    (message: string) => {
      setError(message)
    },
    [],
  )

  const { imports, startImport } = useImportRunner({ api, onFinished: loadSources, onError: reportError })

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
                        <SourceStatusBadge status={current.status} />{' '}
                        {importing && <span className="progress">{current.progress}%</span>}
                        {current.error !== null && <span className="error">{current.error}</span>}
                      </span>
                    ) : source.last_import !== null ? (
                      <SourceStatusBadge status={source.last_import.status} />
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
