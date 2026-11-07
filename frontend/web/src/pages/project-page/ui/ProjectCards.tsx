import { useState } from 'react'
import type { ChangeEvent } from 'react'
import type { ImportStatus, ProjectResource, ProjectStats, WorkspaceModel } from '../../../shared/api/types'
import type { TranslationKey } from '../../../shared/i18n'

type Translate = (key: TranslationKey) => string
type ResourceCategory = 'documentation' | 'user_flow'
type MaterialType = 'archive' | 'markdown'

const IMPORT_STATUS_LABELS: Record<ImportStatus['status'], TranslationKey> = {
  pending: 'sources.statusPending',
  running: 'sources.statusRunning',
  done: 'sources.statusDone',
  failed: 'sources.statusFailed',
}

export function ImportCard({
  t,
  status,
  onRetry,
}: {
  t: Translate
  status: ImportStatus | null
  onRetry: () => void
}) {
  const importing = status?.status === 'pending' || status?.status === 'running'
  const statusLabel = status === null ? 'project.notStarted' : IMPORT_STATUS_LABELS[status.status]
  return (
    <section className="project-card import-card">
      <div className="project-card-heading"><div><h2>{t('project.importTitle')}</h2><p>{t('project.importDescription')}</p></div><span className={`status-dot status-${status?.status ?? 'idle'}`} /></div>
      <div className="project-status-line"><strong>{t(statusLabel)}</strong>{importing && <span>{status.progress}%</span>}</div>
      <div className="progress-track" role="progressbar" aria-label={t('project.importTitle')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={status?.progress ?? 0}><span style={{ width: `${status?.progress ?? 0}%` }} /></div>
      {importing && <small>{t('project.importingFiles')}</small>}
      {status?.status === 'done' && <small className="success-note">{t('project.importComplete')}</small>}
      {status === null && <><small>{t('project.waitingForImport')}</small><button type="button" className="btn project-retry-button" onClick={onRetry}>{t('project.retry')}</button></>}
    </section>
  )
}

export function StatsCard({ t, stats }: { t: Translate; stats: ProjectStats | null }) {
  return (
    <section className="project-card stats-card">
      <div className="project-card-heading"><div><h2>{t('project.statistics')}</h2><p>{t('project.statisticsHint')}</p></div></div>
      <div className="stat-grid"><div className="stat-item"><strong>{stats?.file_count ?? '—'}</strong><span>{t('project.files')}</span></div></div>
    </section>
  )
}

export function ResourcesCard({
  t,
  documentation,
  userFlows,
  uploading,
  onAdd,
  onReplace,
  onOpenMarkdown,
  onDelete,
  onGenerate,
  generationNotice,
  generationModels,
  generationModelId,
  onGenerationModelChange,
}: {
  t: Translate
  documentation: ProjectResource[]
  userFlows: ProjectResource[]
  uploading: ResourceCategory | null
  onAdd: (category: ResourceCategory, type: MaterialType, file: File) => void
  onReplace: (category: ResourceCategory, index: number, file: File) => void
  onOpenMarkdown: (category: ResourceCategory, resource: ProjectResource) => void
  onDelete: (category: ResourceCategory, resource: ProjectResource) => void
  onGenerate: (category: ResourceCategory) => void
  generationNotice: string | null
  generationModels: WorkspaceModel[]
  generationModelId: number | null
  onGenerationModelChange: (modelId: number | null) => void
}) {
  const [selectedTypes, setSelectedTypes] = useState<Record<ResourceCategory, MaterialType>>({
    documentation: 'archive',
    user_flow: 'archive',
  })
  const handleAdd = (category: ResourceCategory) => (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) onAdd(category, selectedTypes[category], file)
    event.currentTarget.value = ''
  }

  const handleReplace = (category: ResourceCategory, index: number) => (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) onReplace(category, index, file)
    event.currentTarget.value = ''
  }

  const renderCategoryActions = (category: ResourceCategory) => (
    <div className="resource-actions resource-add-actions">
      <label className="resource-type-label">{t('sourceForm.typeLabel')}<select value={selectedTypes[category]} onChange={(event) => setSelectedTypes((current) => ({ ...current, [category]: event.target.value as MaterialType }))}>
        <option value="archive">{t('materials.archive')}</option>
        <option value="markdown">{t('materials.markdown')}</option>
      </select></label>
      <label className="btn file-action">{uploading === category ? t('project.uploading') : `+ ${t('project.addResource')}`}<input type="file" accept={selectedTypes[category] === 'archive' ? '.zip,.tar.gz,application/zip,application/gzip' : '.md,text/markdown'} disabled={uploading !== null} onChange={handleAdd(category)} /></label>
      <button type="button" className="btn" disabled={uploading !== null || generationModelId === null} onClick={() => onGenerate(category)}>{t(category === 'documentation' ? 'materials.generateDocumentation' : 'materials.generateUserFlow')}</button>
    </div>
  )

  return (
    <section className="project-card resources-card">
      <div className="project-card-heading"><div><h2>{t('project.context')}</h2><p>{t('project.contextHint')}</p></div></div>
      <label className="generation-model-picker">{t('materials.generationModel')}<select value={generationModelId ?? ''} disabled={generationModels.length === 0} onChange={(event) => onGenerationModelChange(event.target.value ? Number(event.target.value) : null)}>
        <option value="">{t(generationModels.length === 0 ? 'materials.noChatModels' : 'materials.selectGenerationModel')}</option>
        {generationModels.map((model) => <option key={model.id} value={model.id}>{model.display_name} · {model.provider_name}</option>)}
      </select></label>
      <ResourceList title={t('project.documentation')} category="documentation" items={documentation} empty={t('project.noDocumentation')} t={t} onOpenMarkdown={onOpenMarkdown} onDelete={onDelete} onReplace={handleReplace} uploading={uploading} />
      {renderCategoryActions('documentation')}
      <div className="resource-divider" />
      <ResourceList title={t('project.userFlow')} category="user_flow" items={userFlows} empty={t('project.noUserFlows')} t={t} onOpenMarkdown={onOpenMarkdown} onDelete={onDelete} onReplace={handleReplace} uploading={uploading} />
      {renderCategoryActions('user_flow')}
      {generationNotice !== null && <small className="resource-generation-notice" role="status">{generationNotice}</small>}
    </section>
  )
}

export function IndexingCard({ t, canIndex, notice, onIndex, models, selectedModelId, onModelChange }: {
  t: Translate
  canIndex: boolean
  notice: string | null
  onIndex: () => void
  models: WorkspaceModel[]
  selectedModelId: number | null
  onModelChange: (modelId: number | null) => void
}) {
  return (
    <section className="project-card indexing-card">
      <div className="project-card-heading"><div><h2>{t('project.indexing')}</h2><p>{t('project.indexingHint')}</p></div></div>
      <label>{t('project.model')}<select disabled={models.length === 0} value={selectedModelId ?? ''} onChange={(event) => onModelChange(event.target.value ? Number(event.target.value) : null)}>
        <option value="">{t(models.length === 0 ? 'project.modelsComingSoon' : 'project.selectEmbeddingModel')}</option>
        {models.map((model) => <option key={model.id} value={model.id}>{model.display_name} · {model.provider_name}</option>)}
      </select></label>
      <small>{t('project.embeddingModelChangeHint')}</small>
      <div className="index-progress"><span>{t('project.indexStatus')}</span><span>{t('project.notIndexed')}</span></div>
      <div className="progress-track progress-track-muted" role="progressbar" aria-label={t('project.indexing')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={0}><span /></div>
      <button type="button" className="btn btn-primary" disabled={!canIndex || selectedModelId === null} onClick={onIndex}>{t('project.startIndexing')}</button>
      {!canIndex && <small>{t('project.addContextToIndex')}</small>}
      {canIndex && selectedModelId === null && <small>{t('project.selectEmbeddingModel')}</small>}
      {notice !== null && <small className="success-note">{notice}</small>}
    </section>
  )
}

function ResourceList({ title, category, items, empty, t, onOpenMarkdown, onDelete, onReplace, uploading }: {
  title: string
  category: ResourceCategory
  items: ProjectResource[]
  empty: string
  t: Translate
  onOpenMarkdown: (category: ResourceCategory, resource: ProjectResource) => void
  onDelete: (category: ResourceCategory, resource: ProjectResource) => void
  onReplace: (category: ResourceCategory, index: number) => (event: ChangeEvent<HTMLInputElement>) => void
  uploading: ResourceCategory | null
}) {
  return (
    <div className="resource-list">
      <h3>{title}</h3>
      {items.length === 0 ? <p className="resource-empty">{empty}</p> : items.map((item, index) => (
        <div className="resource-item" key={item.id ?? `${item.name}-${index}`}>
          {item.type === 'markdown' && item.id ? (
            <button type="button" className="resource-open" aria-label={`${item.name}: ${t('materials.openEdit')}`} onClick={() => onOpenMarkdown(category, item)}>
              <span className="resource-file-icon">MD</span>
              <span className="resource-name">{item.name}</span>
              <span className="badge">{t('materials.markdown')}</span>
            </button>
          ) : (
            <>
              <span className="resource-file-icon">ZIP</span>
              <span className="resource-name">{item.name}</span>
              <span className="badge">{t('materials.archive')}</span>
            </>
          )}
          {item.type === 'archive' && <label className="btn file-action resource-replace">{uploading === category ? t('project.uploading') : t('materials.replace')}<input type="file" accept=".zip,.tar.gz,application/zip,application/gzip" disabled={uploading !== null} onChange={onReplace(category, index)} /></label>}
          {item.id && <button type="button" className="btn resource-delete" disabled={uploading !== null} onClick={() => onDelete(category, item)}>{t('sources.delete')}</button>}
        </div>
      ))}
    </div>
  )
}
