import { useCallback, useEffect, useState } from 'react'
import { ApiError, getApiClient, getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import type { ImportStatus, ProjectModelSelections, ProjectResource, ProjectStats, Source, WorkspaceModel } from '../../../shared/api/types'
import { useT } from '../../../shared/i18n'
import { materialGeneratorRegistry, MaterialGeneratorUnavailableError } from '../../../shared/materials/generation'
import { ImportCard, IndexingCard, ResourcesCard, StatsCard } from './ProjectCards'
import MarkdownEditor from './MarkdownEditor'
import type { MarkdownResourceReference } from './MarkdownEditor'

type ResourceCategory = 'documentation' | 'user_flow'

interface Props {
  sourceId: number
  api?: ApiClient
  onBack: () => void
  onOpenIssues: () => void
  onNameChange?: (name: string) => void
  launchError?: string | null
}

export default function ProjectPage({ sourceId, api = getApiClient(), onBack, onOpenIssues, onNameChange, launchError = null }: Props) {
  const { t } = useT()
  const [source, setSource] = useState<Source | null>(null)
  const [stats, setStats] = useState<ProjectStats | null>(null)
  const [importStatus, setImportStatus] = useState<ImportStatus | null>(null)
  const [missingPolls, setMissingPolls] = useState(0)
  const [statusPollErrors, setStatusPollErrors] = useState(0)
  const [error, setError] = useState<string | null>(launchError)
  const [uploading, setUploading] = useState<ResourceCategory | null>(null)
  const [indexNotice, setIndexNotice] = useState<string | null>(null)
  const [generationNotice, setGenerationNotice] = useState<string | null>(null)
  const [activeMarkdown, setActiveMarkdown] = useState<MarkdownResourceReference & { content: string } | null>(null)
  const [embeddingModels, setEmbeddingModels] = useState<WorkspaceModel[]>([])
  const [chatModels, setChatModels] = useState<WorkspaceModel[]>([])
  const [modelSelections, setModelSelections] = useState<ProjectModelSelections>({ indexing: null, documentation_generation: null })

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
        const [fetchedSource, loadedStats] = await Promise.all([
          api.getSource(sourceId),
          api.getProjectStats(sourceId),
        ])
        if (cancelled) return
        const currentResources = fetchedSource.config?.resources as Record<string, ProjectResource[]> | undefined
        const resourcesPatch: Record<string, ProjectResource[]> = {}
        for (const category of ['documentation', 'user_flow'] as const) {
          const items = currentResources?.[category] ?? []
          if (items.some((item) => item.id === undefined)) {
            resourcesPatch[category] = items.map((item) => ({ ...item, id: item.id ?? crypto.randomUUID() }))
          }
        }
        const loadedSource = Object.keys(resourcesPatch).length > 0
          ? await api.updateSource(fetchedSource.id, fetchedSource.name, {}, resourcesPatch)
          : fetchedSource
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
    let cancelled = false
    void Promise.all([api.listWorkspaceModels(), api.getProjectModelSelections(sourceId)]).then(([models, selections]) => {
      if (cancelled) return
      setEmbeddingModels(models.filter((model) => model.capabilities.includes('embedding')))
      setChatModels(models.filter((model) => model.capabilities.includes('chat')))
      setModelSelections(selections)
    }).catch((requestError: unknown) => {
      if (!cancelled) setError(getErrorMessage(requestError))
    })
    return () => { cancelled = true }
  }, [api, sourceId])

  const changeModelSelection = async (role: 'indexing' | 'documentation_generation', modelId: number | null) => {
    try {
      setModelSelections(await api.setProjectModelSelection(sourceId, role, modelId))
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    }
  }

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

  const addResource = async (category: ResourceCategory, type: 'archive' | 'markdown', file: File, origin = 'uploaded') => {
    if (source === null) return
    setUploading(category)
    setIndexNotice(null)
    try {
      const uploaded = type === 'markdown' ? await api.uploadMarkdown(file) : await api.uploadArchive(file)
      const resources = source.config?.resources as Record<string, ProjectResource[]> | undefined
      const existing = resources?.[category] ?? []
      const resource: ProjectResource = {
        id: crypto.randomUUID(),
        type,
        name: file.name,
        config: { upload_key: uploaded.upload_key, origin },
      }
      const updated = await api.updateSource(source.id, source.name, {}, {
        [category]: [...existing, resource],
      })
      setSource(updated)
      onNameChange?.(updated.name)
      return resource
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setUploading(null)
    }
  }

  const replaceArchive = async (category: ResourceCategory, index: number, file: File) => {
    if (source === null) return
    setUploading(category)
    try {
      const uploaded = await api.uploadArchive(file)
      const resources = source.config?.resources as Record<string, ProjectResource[]> | undefined
      const existing = [...(resources?.[category] ?? [])]
      const previous = existing[index]
      if (previous === undefined) return
      existing[index] = {
        ...previous,
        id: previous.id ?? crypto.randomUUID(),
        name: file.name,
        config: { ...previous.config, upload_key: uploaded.upload_key, origin: 'uploaded' },
      }
      const updated = await api.updateSource(source.id, source.name, {}, { [category]: existing })
      setSource(updated)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setUploading(null)
    }
  }

  const deleteResource = async (category: ResourceCategory, resource: ProjectResource) => {
    if (source === null || resource.id === undefined || !window.confirm(t('materials.confirmDelete'))) return
    setUploading(category)
    setError(null)
    try {
      await api.deleteResource(source.id, category, resource.id)
      const resources = source.config?.resources as Record<string, ProjectResource[]> | undefined
      setSource({
        ...source,
        config: {
          ...source.config,
          resources: {
            ...resources,
            [category]: (resources?.[category] ?? []).filter((item) => item.id !== resource.id),
          },
        },
      })
      if (activeMarkdown?.resource.id === resource.id) setActiveMarkdown(null)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setUploading(null)
    }
  }

  const openMarkdown = async (category: ResourceCategory, resource: ProjectResource) => {
    if (source === null || resource.id === undefined) return
    try {
      const result = await api.getResourceContent(source.id, category, resource.id)
      setActiveMarkdown({ category, resource, content: result.content })
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    }
  }

  const readMarkdown = async (reference: MarkdownResourceReference): Promise<string> => {
    if (source === null || reference.resource.id === undefined) throw new Error(t('materials.resourceUnavailable'))
    return (await api.getResourceContent(source.id, reference.category, reference.resource.id)).content
  }

  const generateMaterial = async (category: ResourceCategory) => {
    if (source === null) return
    setGenerationNotice(null)
    try {
      const draft = await materialGeneratorRegistry.generate({
        projectId: source.id,
        category,
        source: category === 'documentation' ? 'code' : 'documentation',
      })
      const resource = await addResource(category, 'markdown', new File([draft.content], draft.name, { type: 'text/markdown' }), 'generated')
      if (resource !== undefined && resource.id !== undefined) {
        setActiveMarkdown({ category, resource, content: draft.content })
      }
    } catch (generationError) {
      if (generationError instanceof MaterialGeneratorUnavailableError) {
        setGenerationNotice(t('materials.generationUnavailable'))
      } else {
        setError(getErrorMessage(generationError))
      }
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
          <button type="button" className="btn btn-primary btn-large" onClick={onOpenIssues}>{t('project.goToIssues')}</button>
          {githubUrl !== null && <a className="btn" href={githubUrl} target="_blank" rel="noreferrer">{t('project.openGithub')} ↗</a>}
        </div>
      </div>

      {error !== null && <div className="error page-alert" role="alert">{error}</div>}
      {importStatus?.status === 'failed' && (
        <div className="import-error-panel">
          <div><strong>{t('project.importFailed')}</strong><p>{importStatus.error ?? t('project.unknownImportError')}</p></div>
          <div className="import-error-actions">
            <button type="button" className="btn btn-primary" onClick={() => void startImport()}>{t('project.retry')}</button>
          </div>
        </div>
      )}

      <div className="project-grid">
        <ImportCard t={t} status={importStatus} onRetry={() => void startImport()} />
        <StatsCard t={t} stats={stats} />
        <IndexingCard t={t} canIndex={canIndex} notice={indexNotice} onIndex={() => setIndexNotice(t('project.indexSoon'))} models={embeddingModels} selectedModelId={modelSelections.indexing} onModelChange={(modelId) => void changeModelSelection('indexing', modelId)} />
        <ResourcesCard
          t={t}
          documentation={documentation}
          userFlows={userFlows}
          uploading={uploading}
          generationNotice={generationNotice}
          generationModels={chatModels}
          generationModelId={modelSelections.documentation_generation}
          onGenerationModelChange={(modelId) => void changeModelSelection('documentation_generation', modelId)}
          onAdd={(category, type, file) => void addResource(category, type, file)}
          onReplace={(category, index, file) => void replaceArchive(category, index, file)}
          onOpenMarkdown={(category, resource) => void openMarkdown(category, resource)}
          onDelete={(category, resource) => void deleteResource(category, resource)}
          onGenerate={(category) => void generateMaterial(category)}
        />
      </div>
      {activeMarkdown !== null && (
        <MarkdownEditor
          key={`${activeMarkdown.category}-${activeMarkdown.resource.id}`}
          t={t}
          resource={activeMarkdown.resource}
          content={activeMarkdown.content}
          candidates={[...documentation.map((resource) => ({ category: 'documentation' as const, resource })), ...userFlows.map((resource) => ({ category: 'user_flow' as const, resource }))].filter((reference) => reference.resource.type === 'markdown' && reference.resource.id !== activeMarkdown.resource.id)}
          onRead={readMarkdown}
          onSave={(content) => api.updateResourceContent(source.id, activeMarkdown.category, activeMarkdown.resource.id!, content)}
          onClose={() => setActiveMarkdown(null)}
        />
      )}
    </div>
  )
}
