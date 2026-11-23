import { useEffect, useId, useRef, useState } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import type { ImportStatus, ProjectIndexRun, ProjectIndexType, ProjectResource, ProjectStats, WorkspaceModel } from '../../../shared/api/types'
import type { Lang, TranslationKey } from '../../../shared/i18n'

type Translate = (key: TranslationKey, params?: Record<string, string>) => string
type ResourceCategory = 'documentation' | 'user_flow'

const IMPORT_STATUS_LABELS: Record<ImportStatus['status'], TranslationKey> = {
  pending: 'sources.statusPending',
  running: 'sources.statusRunning',
  done: 'sources.statusDone',
  failed: 'sources.statusFailed',
}

const KNOWLEDGE_SECTIONS = [
  ['code', 'sourceBrowser.title'],
  ['documentation', 'project.documentation'],
  ['user_flow', 'project.userFlow'],
] as const

type KnowledgeSection = typeof KNOWLEDGE_SECTIONS[number][0]

export function ImportCard({
  t,
  lang,
  status,
  onRetry,
}: {
  t: Translate
  lang: Lang
  status: ImportStatus | null
  onRetry: () => void
}) {
  const importing = status?.status === 'pending' || status?.status === 'running'
  const statusLabel = status === null ? 'project.notStarted' : IMPORT_STATUS_LABELS[status.status]
  const progress = new Intl.NumberFormat(lang, { style: 'percent' })
  return (
    <section className="project-card import-card">
      <div className="project-card-heading"><div><h2>{t('project.importTitle')}</h2><p>{t('project.importDescription')}</p></div><span className={`status-dot status-${status?.status ?? 'idle'}`} /></div>
      <div className="project-status-line"><strong>{t(statusLabel)}</strong>{importing && <span>{progress.format(status.progress / 100)}</span>}</div>
      <div className="progress-track" role="progressbar" aria-label={t('project.importTitle')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={status?.progress ?? 0}><span style={{ width: `${status?.progress ?? 0}%` }} /></div>
      {importing && <small>{t('project.importingFiles')}</small>}
      {status?.status === 'done' && <small className="success-note">{t('project.importComplete')}</small>}
      {status === null && <><small>{t('project.waitingForImport')}</small><button type="button" className="btn project-retry-button" onClick={onRetry}>{t('project.retry')}</button></>}
    </section>
  )
}

export function StatsCard({ t, lang, stats, indexes, documentationCount, userFlowCount }: {
  t: Translate
  lang: Lang
  stats: ProjectStats | null
  indexes: ProjectIndexRun[]
  documentationCount: number
  userFlowCount: number
}) {
  const number = new Intl.NumberFormat(lang)
  const indexLabels: Record<ProjectIndexType, TranslationKey> = {
    code: 'project.indexCode',
    documentation: 'project.indexDocumentation',
    user_flow: 'project.indexUserFlow',
  }
  return (
    <section className="project-card stats-card">
      <div className="project-card-heading"><div><h2>{t('project.statistics')}</h2><p>{t('project.statisticsHint')}</p></div></div>
      <div className="stat-grid">
        <div className="stat-item"><strong>{stats === null ? '—' : number.format(stats.file_count)}</strong><span>{t('project.importedFiles')}</span></div>
        <div className="stat-item"><strong>{number.format(documentationCount)}</strong><span>{t('project.documentationFiles')}</span></div>
        <div className="stat-item"><strong>{number.format(userFlowCount)}</strong><span>{t('project.userFlowFiles')}</span></div>
      </div>
      <div className="stats-index-results">
        <h3>{t('project.indexResults')}</h3>
        {indexes.map((index) => <div className="stats-index-row" key={index.index_type}>
          <strong>{t(indexLabels[index.index_type])}</strong>
          {index.run_id === null
            ? <span>{t('project.noIndexResults')}</span>
            : <span>{t('project.indexFilesAndChunks', { files: number.format(index.files_total), chunks: number.format(index.chunks_total) })}</span>}
        </div>)}
      </div>
    </section>
  )
}

export function ResourcesCard({
  t,
  sourceBrowser,
  activeResource,
  reader,
  workspaceError,
  documentation,
  userFlows,
  uploading,
  generationEnabled,
  generatingCategory,
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
  generationNoticeCategory,
}: {
  t: Translate
  sourceBrowser?: ReactNode
  activeResource?: { category: ResourceCategory; id?: string }
  reader?: ReactNode
  workspaceError: string | null
  documentation: ProjectResource[]
  userFlows: ProjectResource[]
  uploading: ResourceCategory | null
  generationEnabled: boolean
  generatingCategory: ResourceCategory | null
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
  generationNoticeCategory: ResourceCategory | null
}) {
  const [section, setSection] = useState<KnowledgeSection>('documentation')
  const [codeOpened, setCodeOpened] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const workspaceId = useId()
  const titleId = useId()
  const dialog = useRef<HTMLDialogElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const opener = useRef<HTMLButtonElement>(null)

  const chooseSection = (next: KnowledgeSection) => {
    setSection(next)
    if (next === 'code') setCodeOpened(true)
  }
  const openWorkspace = (trigger: HTMLButtonElement, next = section) => {
    opener.current = trigger
    chooseSection(next)
    setWorkspaceOpen(true)
  }
  const closeWorkspace = () => {
    dialog.current?.close()
    setWorkspaceOpen(false)
  }
  useEffect(() => {
    if (workspaceOpen) {
      if (!dialog.current?.open) dialog.current?.showModal()
      closeButton.current?.focus()
    } else {
      opener.current?.focus()
      opener.current = null
    }
  }, [workspaceOpen])
  const handleReplace = (category: ResourceCategory, index: number) => (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) onReplace(category, index, file)
    event.currentTarget.value = ''
  }

  const renderCategoryActions = (category: ResourceCategory) => (
    <div className="resource-actions resource-add-actions">
      <button type="button" className="btn" disabled={uploading !== null || generatingCategory !== null || generationModelId === null} onClick={() => onGenerate(category)}>{generatingCategory === category ? t('materials.generating') : t(category === 'documentation' ? 'materials.generateDocumentation' : 'materials.generateUserFlow')}</button>
      {generationNoticeCategory === category && generationNotice !== null && <small className="resource-generation-notice" role="status">{generationNotice}</small>}
    </div>
  )

  return (
    <>
      <section className="project-card resources-card" inert={workspaceOpen}>
        <div className="project-card-heading knowledge-overview-heading">
          <div><h2>{t('project.context')}</h2><p>{t('project.contextHint')}</p></div>
          <button type="button" className="btn btn-primary" aria-haspopup="dialog" aria-controls={workspaceId} onClick={(event) => openWorkspace(event.currentTarget)}>{t('sourceBrowser.openWorkspace')}</button>
        </div>
        <div className="knowledge-sections" role="group" aria-label={t('project.context')}>
          {KNOWLEDGE_SECTIONS.map(([item, label]) => (
            <button key={item} type="button" className="btn" aria-haspopup="dialog" aria-controls={workspaceId} onClick={(event) => openWorkspace(event.currentTarget, item)}>{t(label)}</button>
          ))}
        </div>
        <div className="knowledge-shortcuts">
          {(['documentation', 'user_flow'] as const).flatMap((category) =>
            (category === 'documentation' ? documentation : userFlows)
              .filter((resource) => resource.id && (resource.type === 'markdown' || isTextResource(resource)))
              .slice(0, 3)
              .map((resource) => (
                <button key={`${category}:${resource.id}`} type="button" className="btn" aria-haspopup="dialog" aria-controls={workspaceId} aria-label={t('sourceBrowser.openEditableFile', { name: resource.name })} onClick={(event) => {
                  openWorkspace(event.currentTarget, category)
                  onOpenMarkdown(category, resource)
                }}>{resource.path ?? resource.name}</button>
              )),
          )}
        </div>
      </section>
      <dialog
        ref={dialog}
        id={workspaceId}
        className="knowledge-workspace"
        aria-labelledby={titleId}
        aria-modal="true"
        onCancel={(event) => { event.preventDefault(); closeWorkspace() }}
        onClose={() => setWorkspaceOpen(false)}
      >
        <header className="knowledge-workspace-header">
          <h2 id={titleId}>{t('project.context')}</h2>
          <button ref={closeButton} type="button" className="btn" onClick={closeWorkspace}>{t('sourceBrowser.closeWorkspace')}</button>
        </header>
        <div className="knowledge-sections" role="group" aria-label={t('project.context')}>
          {KNOWLEDGE_SECTIONS.map(([item, label]) => (
            <button key={item} type="button" className="btn" aria-pressed={section === item} onClick={() => chooseSection(item)}>{t(label)}</button>
          ))}
        </div>
        {workspaceError !== null && <p className="error" role="alert">{workspaceError}</p>}
        <div className="knowledge-workspace-body">
          {codeOpened && <div className="knowledge-category" hidden={section !== 'code'}>{sourceBrowser}</div>}
          <div className="knowledge-category" hidden={section === 'code'}>
            {generationEnabled && (
              <div className="knowledge-settings">
                <label className="generation-model-picker">
                  {t('materials.generationModel')}
                  <select value={generationModelId ?? ''} disabled={generationModels.length === 0} onChange={(event) => onGenerationModelChange(event.target.value ? Number(event.target.value) : null)}>
                    <option value="">{t(generationModels.length === 0 ? 'materials.noChatModels' : 'materials.selectGenerationModel')}</option>
                    {generationModels.map((model) => <option key={model.id} value={model.id}>{model.display_name} · {model.provider_name}</option>)}
                  </select>
                </label>
                <small>{t('materials.generationContextHint')}</small>
              </div>
            )}
            {(['documentation', 'user_flow'] as const).map((category) => {
              const isDocs = category === 'documentation'
              const selected = activeResource?.category === category
              return (
                <div key={category} className="knowledge-panes" hidden={section !== category}>
                  <div className="knowledge-list">
                    <ResourceList
                      title={t(isDocs ? 'project.documentation' : 'project.userFlow')}
                      titleHint={isDocs ? undefined : t('project.userFlowHint')}
                      category={category}
                      items={isDocs ? documentation : userFlows}
                      empty={t(isDocs ? 'project.noDocumentation' : 'project.noUserFlows')}
                      selectedId={selected ? activeResource.id : undefined}
                      t={t}
                      onAdd={onAdd}
                      onAddConfluence={isDocs ? onAddConfluence : undefined}
                      onDeleteFolder={onDeleteFolder}
                      onOpenMarkdown={onOpenMarkdown}
                      onDelete={onDelete}
                      onReplace={handleReplace}
                      uploading={uploading}
                    />
                    {isDocs && confluenceNotice !== null && <small className="resource-generation-notice" role="status">{confluenceNotice}</small>}
                    {generationEnabled && renderCategoryActions(category)}
                  </div>
                  {selected ? reader : <KnowledgeEmptyReader t={t} />}
                </div>
              )
            })}
          </div>
        </div>
      </dialog>
    </>
  )
}

export function IndexingCard({ t, lang, indexes, notice, onIndex, canStart, models, selectedModelId, onModelChange }: {
  t: Translate
  lang: Lang
  indexes: ProjectIndexRun[]
  notice: string | null
  onIndex: (indexType: ProjectIndexType) => void
  canStart: (indexType: ProjectIndexType) => boolean
  models: WorkspaceModel[]
  selectedModelId: number | null
  onModelChange: (modelId: number | null) => void
}) {
  const number = new Intl.NumberFormat(lang)
  const indexLabels: Record<ProjectIndexType, TranslationKey> = {
    code: 'project.indexCode',
    documentation: 'project.indexDocumentation',
    user_flow: 'project.indexUserFlow',
  }
  const statusLabels: Record<ProjectIndexRun['status'], TranslationKey> = {
    not_started: 'project.indexNotStarted',
    queued: 'project.indexQueued',
    running: 'project.indexRunning',
    completed: 'project.indexCompleted',
    failed: 'project.indexFailed',
    stale: 'project.indexStale',
  }
  return (
    <section className="project-card indexing-card">
      <div className="project-card-heading"><div><h2>{t('project.indexing')}</h2><p>{t('project.indexingHint')}</p></div></div>
      <label>{t('project.model')}<select disabled={models.length === 0} value={selectedModelId ?? ''} onChange={(event) => onModelChange(event.target.value ? Number(event.target.value) : null)}>
        <option value="">{t('project.selectEmbeddingModel')}</option>
        {models.map((model) => <option key={model.id} value={model.id}>{model.display_name} · {model.provider_name}</option>)}
      </select></label>
      {models.length > 0 && <small>{t('project.embeddingModelChangeHint')}</small>}
      {models.length === 0 && <div className="embedding-setup-hint" role="status"><strong>{t('project.embeddingModelRequired')}</strong><p>{t('project.embeddingModelSetupHint')}</p></div>}
      <div className="index-run-list">
        {indexes.map((index) => {
          const busy = index.status === 'queued' || index.status === 'running'
          return (
            <div className="index-run" key={index.index_type}>
              <div className="index-run-heading">
                <strong>{t(indexLabels[index.index_type])}</strong>
                <span className={`index-state index-state-${index.status}`}>{t(statusLabels[index.status])}</span>
              </div>
              <div className="progress-track progress-track-muted" role="progressbar" aria-label={t(indexLabels[index.index_type])} aria-valuemin={0} aria-valuemax={100} aria-valuenow={index.progress}><span style={{ width: `${index.progress}%` }} /></div>
              {index.status === 'completed' && <small>{t('project.indexChunkCount', { count: number.format(index.chunks_total) })}</small>}
              {index.status === 'failed' && index.error !== null && <small className="error">{index.error}</small>}
              <button type="button" className="btn btn-primary" disabled={!canStart(index.index_type) || selectedModelId === null || busy} onClick={() => onIndex(index.index_type)}>{busy ? t('project.indexRunning') : index.status === 'completed' ? t('project.reindex') : t('project.startIndexing')}</button>
              {!canStart(index.index_type) && <small>{t(index.index_type === 'code' ? 'project.importBeforeIndex' : index.index_type === 'documentation' ? 'project.addDocumentationBeforeIndex' : 'project.addUserFlowBeforeIndex')}</small>}
            </div>
          )
        })}
      </div>
      {selectedModelId === null && models.length > 0 && <small>{t('project.selectEmbeddingModel')}</small>}
      {notice !== null && <small className="success-note">{notice}</small>}
    </section>
  )
}

export function KnowledgeEmptyReader({ t }: { t: Translate }) {
  return <div className="knowledge-reader knowledge-reader-empty">{t('sourceBrowser.selectFile')}</div>
}

function ResourceList({ title, titleHint, category, items, empty, selectedId, t, onAdd, onAddConfluence, onDeleteFolder, onOpenMarkdown, onDelete, onReplace, uploading }: {
  title: string
  titleHint?: string
  category: ResourceCategory
  items: ProjectResource[]
  empty: string
  selectedId?: string
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
  const [documentationSource, setDocumentationSource] = useState<'local' | 'confluence'>('local')
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
          <button type="button" className="btn resource-folder-delete" aria-label={t('sourceBrowser.deleteFolder', { name: node.name })} title={t('sources.delete')} disabled={uploading !== null} onClick={() => onDeleteFolder(category, path)}><TrashIcon /></button>
          <label className="btn resource-tree-add" title={t('materials.localFile')}><span aria-hidden="true">+</span><input type="file" aria-label={t('materials.localFile')} disabled={uploading !== null} onChange={selectFile(path)} /></label>
        </div>
        {isExpanded && renderNodes(node.children, path, depth + 1)}
      </div>
    }
    const { item, index } = node
    if (item === undefined || index === undefined) return null
    return <div className="resource-item" key={item.id ?? `${node.name}-${index}`} style={{ paddingLeft: `${depth * 18 + 22}px` }}>
      {(item.type === 'markdown' || isTextResource(item)) && item.id ? <button type="button" className="resource-open" aria-current={item.id === selectedId ? 'true' : undefined} aria-label={t('sourceBrowser.openEditableFile', { name: node.name })} onClick={() => onOpenMarkdown(category, item)}><span className="resource-file-icon">{item.type === 'markdown' ? 'MD' : fileIcon(node.name)}</span><span className="resource-name">{node.name}</span></button> : <><span className="resource-file-icon">{item.type === 'archive' ? 'ZIP' : fileIcon(node.name)}</span><span className="resource-name">{node.name}</span></>}
      {item.type === 'archive' && <label className="btn file-action resource-replace">{uploading === category ? t('project.uploading') : t('materials.replace')}<input type="file" accept=".zip,.tar,.tar.gz,.tgz,application/zip,application/gzip" disabled={uploading !== null} onChange={onReplace(category, index)} /></label>}
      {item.id && <button type="button" className="btn resource-delete" aria-label={t('sourceBrowser.deleteFile', { name: node.name })} title={t('sources.delete')} disabled={uploading !== null} onClick={() => onDelete(category, item)}><TrashIcon /></button>}
    </div>
  })
  return (
    <div className="resource-list">
      <div className="resource-tree-root-row">
        <div className="resource-tree-title"><h3>{title}</h3>{titleHint !== undefined && <small className="resource-title-hint">{titleHint}</small>}</div>
        <div className="resource-tree-root-actions">
          {category === 'documentation' && <select aria-label={t('materials.sourceType')} value={documentationSource} onChange={(event) => setDocumentationSource(event.target.value as 'local' | 'confluence')}><option value="local">{t('materials.sourceLocal')}</option><option value="confluence">{t('materials.sourceConfluence')}</option></select>}
          <label className="btn resource-tree-add resource-tree-root-add" title={documentationSource === 'confluence' && category === 'documentation' ? t('materials.sourceConfluence') : t('materials.localFile')} onClick={(event) => {
            if (category === 'documentation' && documentationSource === 'confluence') {
              event.preventDefault()
              onAddConfluence?.()
            }
          }}><span aria-hidden="true">+</span><input type="file" aria-label={t('materials.localFile')} disabled={uploading !== null || (category === 'documentation' && documentationSource === 'confluence')} onChange={selectFile('')} /></label>
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
