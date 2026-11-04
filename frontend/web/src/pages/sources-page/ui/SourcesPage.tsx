import { useCallback, useEffect, useState } from 'react'
import { getApiClient, getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import { SourceStatusBadge } from '../../../entities/source'
import type { Source } from '../../../entities/source'
import { useT } from '../../../shared/i18n'
import SourceForm from '../../../features/add-source'

interface Props {
  api?: ApiClient
  onProjectSelected?: (sourceId: number) => void
  onProjectCreated?: (source: Source, importError?: string) => void
}

export default function SourcesPage({ api = getApiClient(), onProjectSelected, onProjectCreated }: Props) {
  const { t } = useT()
  const [sources, setSources] = useState<Source[]>([])
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editingSource, setEditingSource] = useState<Source | null>(null)
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
        <div>
          <span className="eyebrow">{t('app.workspace')}</span>
          <h1>{t('common.sources')}</h1>
          <p>{t('sources.description')}</p>
        </div>
        <button type="button" className="btn btn-primary btn-large" onClick={() => setShowForm(true)}>
          <span aria-hidden="true">+</span>{t('sources.add')}
        </button>
      </div>
      {error !== null && <p className="error page-alert" role="alert">{error}</p>}
      {loaded && sources.length === 0 && (
        <div className="empty-state">
          <div>
            <div className="empty-state-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10v6H4V5.5ZM4 12h6v8H5.5A1.5 1.5 0 0 1 4 18.5V12Zm8-8h6.5A1.5 1.5 0 0 1 20 5.5V10h-8V4Zm0 8h8v6.5a1.5 1.5 0 0 1-1.5 1.5H12v-8Z" /></svg></div>
            <h3>{t('sources.emptyTitle')}</h3>
            <p>{t('sources.empty')}</p>
            <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>{t('sources.add')}</button>
          </div>
        </div>
      )}
      {sources.length > 0 && (
        <>
        <p className="section-label">{t('sources.listHeading')} <span className="badge">{sources.length}</span></p>
        <div className="table-card">
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
              return (
                <tr
                  key={source.id}
                  className="project-row"
                  role="link"
                  tabIndex={0}
                  onClick={() => onProjectSelected?.(source.id)}
                  onKeyDown={(event) => {
                    if (event.target !== event.currentTarget) return
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      onProjectSelected?.(source.id)
                    }
                  }}
                >
                  <td><button type="button" className="project-name-button" onClick={() => onProjectSelected?.(source.id)}>{source.name}</button></td>
                  <td>{source.type}</td>
                  <td>
                    {source.last_import !== null ? (
                      <SourceStatusBadge status={source.last_import.status} />
                    ) : (
                      <span>—</span>
                    )}
                  </td>
                  <td>{source.enabled ? t('common.yes') : t('common.no')}</td>
                  <td onClick={(event) => event.stopPropagation()}>
                    <button type="button" className="btn" onClick={() => setEditingSource(source)}>
                      {t('sources.edit')}
                    </button>
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
        </div>
        </>
      )}
      {showForm && (
        <div className="modal-overlay">
          <div className="modal">
            <h2>{t('sources.add')}</h2>
            <SourceForm
              api={api}
              onCreated={(created, importError) => {
                setShowForm(false)
                onProjectCreated?.(created, importError)
                void loadSources()
              }}
              onClose={() => setShowForm(false)}
            />
          </div>
        </div>
      )}
      {editingSource !== null && (
        <div className="modal-overlay">
          <div className="modal">
            <h2>{t('project.editTitle')}</h2>
            <SourceForm
              api={api}
              source={editingSource}
              onCreated={(updated, importError) => {
                setEditingSource(null)
                setSources((current) => current.map((item) => item.id === updated.id ? updated : item))
                void loadSources().then(() => setError(importError ?? null))
              }}
              onClose={() => setEditingSource(null)}
            />
          </div>
        </div>
      )}
    </div>
  )
}
