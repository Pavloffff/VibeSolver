import { useCallback, useEffect, useState } from 'react'
import { ApiError, getApiClient, getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import type { ImportStatus, ProjectResource, ProjectStats, Source } from '../../../shared/api/types'
import { useT } from '../../../shared/i18n'
import SourceForm from '../../../features/add-source'
import { ImportCard, IndexingCard, IssuesCard, ResourcesCard, StatsCard } from './ProjectCards'

type ResourceCategory = 'documentation' | 'user_flow'

interface Props {
  sourceId: number
  api?: ApiClient
  onBack: () => void
  onNameChange?: (name: string) => void
  launchError?: string | null
}

export default function ProjectPage({ sourceId, api = getApiClient(), onBack, onNameChange, launchError = null }: Props) {
  const { t } = useT()
  const [source, setSource] = useState<Source | null>(null)
  const [stats, setStats] = useState<ProjectStats | null>(null)
  const [importStatus, setImportStatus] = useState<ImportStatus | null>(null)
  const [missingPolls, setMissingPolls] = useState(0)
  const [statusPollErrors, setStatusPollErrors] = useState(0)
  const [error, setError] = useState<string | null>(launchError)
  const [uploading, setUploading] = useState<ResourceCategory | null>(null)
  const [editing, setEditing] = useState(false)
  const [indexNotice, setIndexNotice] = useState<string | null>(null)
  const [issueNotice, setIssueNotice] = useState<string | null>(null)

  const refreshStats = useCallback(async () => {
    setStats(await api.getProjectStats(sourceId))
  }, [api, sourceId])

  const startImport = useCallback(async () => {
    setError(null)
    setStatusPollErrors(0)
    setImportStatus({ status: 'pending', progress: 0, error: null })
    try {
      await api.startImport(sourceId)
    } catch (requestError) {
      setImportStatus(null)
      setError(getErrorMessage(requestError))
    }
  }, [api, sourceId])

  useEffect(() => {
    if (source === null || importStatus !== null || error !== null || missingPolls >= 6) return
    let cancelled = false
    const timer = setTimeout(() => {
      void api.getImportStatus(sourceId).then((status) => {
        if (!cancelled) setImportStatus(status)
      }).catch((requestError: unknown) => {
        if (cancelled) return
        if (requestError instanceof ApiError && requestError.status === 404) {
          setMissingPolls((count) => count + 1)
        } else {
          setError(getErrorMessage(requestError))
        }
      })
    }, 1100)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [api, error, importStatus, missingPolls, source, sourceId])

  useEffect(() => {
    if (missingPolls >= 6 && importStatus === null && error === null) setError(t('project.importNotStarted'))
  }, [error, importStatus, missingPolls, t])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const [loadedSource, loadedStats] = await Promise.all([
          api.getSource(sourceId),
          api.getProjectStats(sourceId),
        ])
        if (cancelled) return
        setSource(loadedSource)
        onNameChange?.(loadedSource.name)
        setStats(loadedStats)
        try {
          setImportStatus(await api.getImportStatus(sourceId))
        } catch (requestError) {
          if (cancelled) return
          if (requestError instanceof ApiError && requestError.status === 404) {
            setImportStatus(null)
          } else {
            setError(getErrorMessage(requestError))
          }
        }
      } catch (requestError) {
        if (!cancelled) setError(getErrorMessage(requestError))
      }
    }
    void load()
    return () => { cancelled = true }
  }, [api, onNameChange, sourceId])

  useEffect(() => {
    if (importStatus?.status !== 'pending' && importStatus?.status !== 'running') return
    let cancelled = false
    const timer = setTimeout(() => {
      void api.getImportStatus(sourceId).then((nextStatus) => {
        if (cancelled) return
        setStatusPollErrors(0)
        setImportStatus(nextStatus)
        if (nextStatus.status === 'done' || nextStatus.status === 'failed') {
          void refreshStats().catch((requestError: unknown) => setError(getErrorMessage(requestError)))
        }
      }).catch((requestError: unknown) => {
        if (cancelled) return
        if (requestError instanceof ApiError && requestError.status === 404) {
          setStatusPollErrors((count) => count + 1)
          if (statusPollErrors >= 4) {
            setImportStatus(null)
            setError(t('project.importNotStarted'))
          }
        } else {
          setError(getErrorMessage(requestError))
        }
      })
    }, 1600)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [api, importStatus?.progress, importStatus?.status, refreshStats, sourceId, statusPollErrors, t])

  const addResource = async (category: ResourceCategory, file: File) => {
    if (source === null) return
    setUploading(category)
    setIndexNotice(null)
    try {
      const uploaded = await api.uploadArchive(file)
      const resources = source.config?.resources as Record<string, ProjectResource[]> | undefined
      const existing = resources?.[category] ?? []
      const updated = await api.updateSource(source.id, source.name, {}, {
        [category]: [...existing, { type: 'archive', name: file.name, config: { upload_key: uploaded.upload_key } }],
      })
      setSource(updated)
      onNameChange?.(updated.name)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setUploading(null)
    }
  }

  const repoUrl = typeof source?.config?.url === 'string' ? source.config.url : null
  const githubUrl = repoUrl !== null ? (() => {
    try {
      const parsed = new URL(repoUrl)
      return parsed.hostname.toLowerCase() === 'github.com' ? repoUrl : null
    } catch {
      return null
    }
  })() : null
  const resources = source?.config?.resources as Record<string, ProjectResource[]> | undefined
  const documentation = resources?.documentation ?? []
  const userFlows = resources?.user_flow ?? []
  const canIndex = documentation.length > 0 || userFlows.length > 0

  if (source === null) {
    return <div className="project-loading"><button type="button" className="text-button" onClick={onBack}>← {t('project.back')}</button><p>{error ?? t('project.loading')}</p></div>
  }

  return (
    <div className="project-page">
      <div className="project-heading">
        <div>
          <span className="eyebrow">{t('app.workspace')}</span>
          <div className="project-title-row"><h1>{source.name}</h1><span className="badge">{source.type}</span></div>
          <p>{t('project.subtitle')}</p>
        </div>
        <div className="project-heading-actions">
          {githubUrl !== null && <a className="btn" href={githubUrl} target="_blank" rel="noreferrer">{t('project.openGithub')} ↗</a>}
          <button type="button" className="btn" onClick={() => setEditing(true)}>{t('project.edit')}</button>
        </div>
      </div>

      {error !== null && <div className="error page-alert" role="alert">{error}</div>}
      {importStatus?.status === 'failed' && (
        <div className="import-error-panel">
          <div><strong>{t('project.importFailed')}</strong><p>{importStatus.error ?? t('project.unknownImportError')}</p></div>
          <div className="import-error-actions">
            <button type="button" className="btn" onClick={() => setEditing(true)}>{t('project.editAndRetry')}</button>
            <button type="button" className="btn btn-primary" onClick={() => void startImport()}>{t('project.retry')}</button>
          </div>
        </div>
      )}

      <div className="project-grid">
        <ImportCard t={t} status={importStatus} onRetry={() => void startImport()} />
        <StatsCard t={t} stats={stats} />
        <ResourcesCard t={t} documentation={documentation} userFlows={userFlows} uploading={uploading} onAdd={(category, file) => void addResource(category, file)} />
        <IndexingCard t={t} canIndex={canIndex} notice={indexNotice} onIndex={() => setIndexNotice(t('project.indexSoon'))} />
        <IssuesCard t={t} notice={issueNotice} onAdd={() => setIssueNotice(t('project.issuesSoon'))} />
      </div>

              {editing && <div className="modal-overlay"><div className="modal"><h2>{t('project.editTitle')}</h2><SourceForm api={api} source={source} onCreated={(updated, importError) => { setSource(updated); onNameChange?.(updated.name); setEditing(false); setError(importError ?? null); if (importError === undefined) setImportStatus({ status: 'pending', progress: 0, error: null }) }} onClose={() => setEditing(false)} /></div></div>}
    </div>
  )
}
