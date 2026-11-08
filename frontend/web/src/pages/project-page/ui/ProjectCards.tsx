import { useState } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import type { ImportStatus, ProjectResource, ProjectStats, WorkspaceModel } from '../../../shared/api/types'
import type { TranslationKey } from '../../../shared/i18n'

type Translate = (key: TranslationKey) => string
type ResourceCategory = 'documentation' | 'user_flow'

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
  onDeleteFolder,
  onGenerate,
  generationNotice,
  confluenceNotice,
  onAddConfluence,
  generationModels,
  generationModelId,
  onGenerationModelChange,
}: {
  t: Translate
  documentation: ProjectResource[]
  userFlows: ProjectResource[]
  uploading: ResourceCategory | null
  onAdd: (category: ResourceCategory, file: File, parentPath?: string) => void
  onReplace: (category: ResourceCategory, index: number, file: File) => void
  onOpenMarkdown: (category: ResourceCategory, resource: ProjectResource) => void
  onDelete: (category: ResourceCategory, resource: ProjectResource) => void
  onDeleteFolder: (category: ResourceCategory, path: string) => void
  onGenerate: (category: ResourceCategory) => void
  generationNotice: string | null
  confluenceNotice: string | null
  onAddConfluence: () => void
  generationModels: WorkspaceModel[]
  generationModelId: number | null
  onGenerationModelChange: (modelId: number | null) => void
}) {
  const handleReplace = (category: ResourceCategory, index: number) => (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) onReplace(category, index, file)
    event.currentTarget.value = ''
  }

  const renderCategoryActions = (category: ResourceCategory) => (
    <div className="resource-actions resource-add-actions">
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
      <ResourceList title={t('project.documentation')} category="documentation" items={documentation} empty={t('project.noDocumentation')} t={t} onAdd={onAdd} onAddConfluence={onAddConfluence} onDeleteFolder={onDeleteFolder} onOpenMarkdown={onOpenMarkdown} onDelete={onDelete} onReplace={handleReplace} uploading={uploading} />
      {confluenceNotice !== null && <small className="resource-generation-notice" role="status">{confluenceNotice}</small>}
      {renderCategoryActions('documentation')}
      <div className="resource-divider" />
      <ResourceList title={t('project.userFlow')} category="user_flow" items={userFlows} empty={t('project.noUserFlows')} t={t} onAdd={onAdd} onDeleteFolder={onDeleteFolder} onOpenMarkdown={onOpenMarkdown} onDelete={onDelete} onReplace={handleReplace} uploading={uploading} />
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

function ResourceList({ title, category, items, empty, t, onAdd, onAddConfluence, onDeleteFolder, onOpenMarkdown, onDelete, onReplace, uploading }: {
  title: string
  category: ResourceCategory
  items: ProjectResource[]
  empty: string
  t: Translate
  onAdd: (category: ResourceCategory, file: File, parentPath?: string) => void
  onAddConfluence?: () => void
  onDeleteFolder: (category: ResourceCategory, path: string) => void
  onOpenMarkdown: (category: ResourceCategory, resource: ProjectResource) => void
  onDelete: (category: ResourceCategory, resource: ProjectResource) => void
  onReplace: (category: ResourceCategory, index: number) => (event: ChangeEvent<HTMLInputElement>) => void
  uploading: ResourceCategory | null
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(['']))
  const nodes = buildResourceTree(items)
  const selectFile = (parentPath: string) => (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) onAdd(category, file, parentPath)
    event.currentTarget.value = ''
  }
  const renderNodes = (children: ResourceTreeNode[], parentPath: string, depth: number): ReactNode => children.map((node) => {
    if (node.children !== null) {
      const path = [parentPath, node.name].filter(Boolean).join('/')
      const isExpanded = expanded.has(path)
      return <div key={path} className="resource-tree-folder">
        <div className="resource-tree-row" style={{ paddingLeft: `${depth * 18}px` }}>
          <button type="button" className="resource-tree-toggle" aria-label={t(isExpanded ? 'materials.collapseFolder' : 'materials.expandFolder').replace('{name}', node.name)} onClick={() => setExpanded((current) => {
            const next = new Set(current)
            if (isExpanded) next.delete(path)
            else next.add(path)
            return next
          })}>{isExpanded ? '▾' : '▸'} 📁 {node.name}</button>
          <button type="button" className="btn resource-folder-delete" aria-label={`${t('materials.deleteFolder')}: ${node.name}`} title={t('sources.delete')} disabled={uploading !== null} onClick={() => onDeleteFolder(category, path)}><TrashIcon /></button>
          <label className="btn resource-tree-add" title={t('materials.localFile')}><span aria-hidden="true">+</span><input type="file" aria-label={t('materials.localFile')} disabled={uploading !== null} onChange={selectFile(path)} /></label>
        </div>
        {isExpanded && renderNodes(node.children, path, depth + 1)}
      </div>
    }
    const { item, index } = node
    if (item === undefined || index === undefined) return null
    return <div className="resource-item" key={item.id ?? `${node.name}-${index}`} style={{ paddingLeft: `${depth * 18 + 22}px` }}>
      {(item.type === 'markdown' || isTextResource(item)) && item.id ? <button type="button" className="resource-open" aria-label={`${node.name}: ${t('materials.openEdit')}`} onClick={() => onOpenMarkdown(category, item)}><span className="resource-file-icon">{item.type === 'markdown' ? 'MD' : fileIcon(node.name)}</span><span className="resource-name">{node.name}</span></button> : <><span className="resource-file-icon">{item.type === 'archive' ? 'ZIP' : fileIcon(node.name)}</span><span className="resource-name">{node.name}</span></>}
      {item.type === 'archive' && <label className="btn file-action resource-replace">{uploading === category ? t('project.uploading') : t('materials.replace')}<input type="file" accept=".zip,.tar,.tar.gz,.tgz,application/zip,application/gzip" disabled={uploading !== null} onChange={onReplace(category, index)} /></label>}
      {item.id && <button type="button" className="btn resource-delete" aria-label={`${t('sources.delete')}: ${node.name}`} title={t('sources.delete')} disabled={uploading !== null} onClick={() => onDelete(category, item)}><TrashIcon /></button>}
    </div>
  })
  return (
    <div className="resource-list">
      <div className="resource-tree-root-row">
        <h3>{title}</h3>
        <div className="resource-tree-root-actions">
          {category === 'documentation' && <button type="button" className="btn resource-confluence-add" onClick={onAddConfluence}>{t('materials.addConfluence')}</button>}
          <label className="btn resource-tree-add" title={t('materials.localFile')}><span aria-hidden="true">+</span><input type="file" aria-label={t('materials.localFile')} disabled={uploading !== null} onChange={selectFile('')} /></label>
        </div>
      </div>
      {items.length === 0 ? <p className="resource-empty">{empty}</p> : renderNodes(nodes, '', 0)}
    </div>
  )
}

function isTextResource(resource: ProjectResource): boolean {
  const contentType = resource.config.content_type
  const extensionless = !resource.name.split('/').at(-1)?.includes('.')
  return resource.type === 'file' && (resource.config.text === true || extensionless || (typeof contentType === 'string' && (contentType.startsWith('text/') || contentType.includes('json') || contentType.includes('xml') || contentType.includes('yaml'))))
}

function fileIcon(name: string): string {
  const extension = name.split('.').at(-1)?.slice(0, 3).toUpperCase()
  return extension && extension !== name.toUpperCase() ? extension : 'TXT'
}

function TrashIcon() {
  return <svg aria-hidden="true" className="resource-trash-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3" />
  </svg>
}

interface ResourceTreeNode { name: string; children: ResourceTreeNode[] | null; item?: ProjectResource; index?: number }

function buildResourceTree(items: ProjectResource[]): ResourceTreeNode[] {
  const roots: ResourceTreeNode[] = []
  items.forEach((item, index) => {
    const path = item.path ?? item.name
    const parts = path.split('/').filter(Boolean)
    let nodes = roots
    parts.forEach((part, partIndex) => {
      let node = nodes.find((candidate) => candidate.name === part)
      if (node === undefined) {
        node = { name: part, children: partIndex === parts.length - 1 ? null : [] }
        nodes.push(node)
      }
      if (partIndex === parts.length - 1) { node.children = null; node.item = item; node.index = index }
      else if (node.children === null) node.children = []
      nodes = node.children ?? []
    })
  })
  const sort = (nodes: ResourceTreeNode[]) => { nodes.sort((a, b) => Number(a.children === null) - Number(b.children === null) || a.name.localeCompare(b.name)); nodes.forEach((node) => { if (node.children) sort(node.children) }) }
  sort(roots)
  return roots
}
