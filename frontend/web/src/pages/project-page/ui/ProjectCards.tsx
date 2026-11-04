import type { ChangeEvent } from 'react'
import type { ImportStatus, ProjectResource, ProjectStats } from '../../../shared/api/types'
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
}: {
  t: Translate
  documentation: ProjectResource[]
  userFlows: ProjectResource[]
  uploading: ResourceCategory | null
  onAdd: (category: ResourceCategory, file: File) => void
}) {
  const handleChange = (category: ResourceCategory) => (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) onAdd(category, file)
    event.currentTarget.value = ''
  }
  return (
    <section className="project-card resources-card">
      <div className="project-card-heading"><div><h2>{t('project.context')}</h2><p>{t('project.contextHint')}</p></div></div>
      <ResourceList title={t('project.documentation')} items={documentation} empty={t('project.noDocumentation')} />
      <label className="resource-type-label">{t('sourceForm.typeLabel')}<select value="archive" onChange={() => {}}><option value="archive">{t('project.archiveSourceType')}</option></select></label>
      <div className="resource-actions"><label className="btn file-action">{uploading === 'documentation' ? t('project.uploading') : `+ ${t('project.addDocumentation')}`}<input type="file" accept=".zip,.tar.gz,application/zip,application/gzip" disabled={uploading !== null} onChange={handleChange('documentation')} /></label></div>
      <div className="resource-divider" />
      <ResourceList title={t('project.userFlow')} items={userFlows} empty={t('project.noUserFlows')} />
      <label className="resource-type-label">{t('sourceForm.typeLabel')}<select value="archive" onChange={() => {}}><option value="archive">{t('project.archiveSourceType')}</option></select></label>
      <div className="resource-actions"><label className="btn file-action">{uploading === 'user_flow' ? t('project.uploading') : `+ ${t('project.addUserFlow')}`}<input type="file" accept=".zip,.tar.gz,application/zip,application/gzip" disabled={uploading !== null} onChange={handleChange('user_flow')} /></label></div>
    </section>
  )
}

export function IndexingCard({ t, canIndex, notice, onIndex }: { t: Translate; canIndex: boolean; notice: string | null; onIndex: () => void }) {
  return (
    <section className="project-card indexing-card">
      <div className="project-card-heading"><div><h2>{t('project.indexing')}</h2><p>{t('project.indexingHint')}</p></div></div>
      <label>{t('project.model')}<select disabled value=""><option value="">{t('project.modelsComingSoon')}</option></select></label>
      <div className="index-progress"><span>{t('project.indexStatus')}</span><span>{t('project.notIndexed')}</span></div>
      <div className="progress-track progress-track-muted" role="progressbar" aria-label={t('project.indexing')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={0}><span /></div>
      <button type="button" className="btn btn-primary" disabled={!canIndex} onClick={onIndex}>{t('project.startIndexing')}</button>
      {!canIndex && <small>{t('project.addContextToIndex')}</small>}
      {notice !== null && <small className="success-note">{notice}</small>}
    </section>
  )
}

export function IssuesCard({ t, notice, onAdd }: { t: Translate; notice: string | null; onAdd: () => void }) {
  return (
    <section className="project-card issues-card">
      <div className="project-card-heading"><div><h2>{t('project.issues')}</h2><p>{t('project.issuesHint')}</p></div><span className="badge badge-muted">{t('project.comingSoon')}</span></div>
      <div className="issues-empty"><span className="empty-state-icon">＋</span><p>{t('project.noIssues')}</p></div>
      <button type="button" className="btn" onClick={onAdd}>{t('project.addIssue')}</button>
      {notice !== null && <small className="success-note issue-notice">{notice}</small>}
    </section>
  )
}

function ResourceList({ title, items, empty }: { title: string; items: ProjectResource[]; empty: string }) {
  return <div className="resource-list"><h3>{title}</h3>{items.length === 0 ? <p className="resource-empty">{empty}</p> : items.map((item, index) => <div className="resource-item" key={`${item.name}-${index}`}><span className="resource-file-icon">ZIP</span><span>{item.name}</span><span className="badge">{item.type}</span></div>)}</div>
}
