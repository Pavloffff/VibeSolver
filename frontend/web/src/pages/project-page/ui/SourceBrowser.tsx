import { lazy, Suspense, useEffect, useId, useState } from 'react'
import type { ReactNode } from 'react'
import type { ApiClient } from '../../../shared/api/client'
import type { SourceBrowserFile, SourceBrowserSnapshot, SourceBrowserTree } from '../../../shared/api/types'
import type { TranslationKey } from '../../../shared/i18n'
import { KnowledgeEmptyReader } from './ProjectCards'
import './sourceBrowser.css'

const HighlightedCode = lazy(() => import('./HighlightedCode'))

type BrowserApi = Pick<ApiClient, 'getSourceBrowserSnapshot' | 'getSourceBrowserTree' | 'getSourceBrowserFile'>
type Translate = (key: TranslationKey) => string

interface BrowserProps {
  sourceId: number
  api: BrowserApi
  t: Translate
}

interface SnapshotProps extends BrowserProps {
  snapshotId: number
  branch: string
}

export function SourceBrowser(props: BrowserProps) {
  const [request, setRequest] = useState(0)
  return (
    <SourceSnapshot key={`${props.sourceId}:${request}`} {...props} onRefresh={() => setRequest((current) => current + 1)} />
  )
}

function SourceSnapshot({ sourceId, api, t, onRefresh }: BrowserProps & { onRefresh: () => void }) {
  const [snapshot, setSnapshot] = useState<SourceBrowserSnapshot | 'error' | null>(null)
  const [selectedBranch, setSelectedBranch] = useState<string | null>(null)

  useEffect(() => {
    const request = new AbortController()
    api.getSourceBrowserSnapshot(sourceId, request.signal).then(
      (result) => { if (!request.signal.aborted) setSnapshot(result) },
      () => { if (!request.signal.aborted) setSnapshot('error') },
    )
    return () => request.abort()
  }, [sourceId, api])

  const ready = snapshot !== null && snapshot !== 'error' && snapshot.status === 'ready' ? snapshot : null
  const snapshotId = ready?.snapshot_id
  const branch = selectedBranch ?? ready?.branches[0] ?? ''
  const toolbar = (
    <div className="resource-tree-root-row source-browser-toolbar">
      <h3>{t('sourceBrowser.title')}</h3>
      {snapshotId != null && <small>{t('sourceBrowser.snapshot')} #{snapshotId}</small>}
      <div className="resource-tree-root-actions">
        {ready?.branches.some(Boolean) && <label className="source-browser-branch">
          {t('sourceBrowser.branch')}
          <select value={branch} onChange={(event) => setSelectedBranch(event.target.value)}>
            {ready.branches.map((item) => <option key={item} value={item}>{item || t('sourceBrowser.noBranch')}</option>)}
          </select>
        </label>}
        <button type="button" className="btn" onClick={onRefresh}>{t('sourceBrowser.refresh')}</button>
      </div>
    </div>
  )
  if (snapshotId != null) return <SourceBranch key={branch} sourceId={sourceId} snapshotId={snapshotId} branch={branch} api={api} t={t} toolbar={toolbar} />
  return (
    <div className="knowledge-panes">
      <div className="knowledge-list resource-list">
        {toolbar}
        {snapshot === null ? <p className="resource-empty" role="status">{t('sourceBrowser.loading')}</p>
          : snapshot === 'error' || snapshot.status === 'ready' ? <p className="resource-empty" role="alert">{t('sourceBrowser.error')}</p>
          : <p className="resource-empty" role="status">{t(`sourceBrowser.${snapshot.status}`)}</p>}
      </div>
      <KnowledgeEmptyReader t={t} />
    </div>
  )
}

function SourceBranch({ toolbar, ...props }: SnapshotProps & { toolbar: ReactNode }) {
  const [folder, setFolder] = useState('')
  const [file, setFile] = useState<string | null>(null)
  const selectFolder = (path: string) => {
    setFolder(path)
    setFile(null)
  }
  const crumbs = folder ? folder.split('/') : []
  return (
    <div className="knowledge-panes">
      <div className="knowledge-list resource-list">
        {toolbar}
        <div className="source-browser-crumbs">
          <button type="button" className="text-button" onClick={() => selectFolder('')}>{props.t('sourceBrowser.root')}</button>
          {crumbs.map((part, index) => {
            const path = crumbs.slice(0, index + 1).join('/')
            return <span key={path}><span aria-hidden="true"> / </span>
              <button type="button" className="text-button" onClick={() => selectFolder(path)}>{part}</button>
            </span>
          })}
        </div>
        <SourceFolder key={folder} {...props} folder={folder} file={file} onFolder={selectFolder} onFile={setFile} />
      </div>
      {file === null ? <KnowledgeEmptyReader t={props.t} /> : <SourceFile key={file} {...props} path={file} />}
    </div>
  )
}

function SourceFolder({ sourceId, snapshotId, branch, api, t, folder, file, onFolder, onFile }: SnapshotProps & {
  folder: string
  file: string | null
  onFolder: (path: string) => void
  onFile: (path: string) => void
}) {
  const [tree, setTree] = useState<SourceBrowserTree | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    const request = new AbortController()
    api.getSourceBrowserTree(sourceId, snapshotId, branch, folder, null, request.signal).then(
      (result) => { if (!request.signal.aborted) setTree(result) },
      () => { if (!request.signal.aborted) setError(true) },
    )
    return () => request.abort()
  }, [sourceId, snapshotId, branch, folder, api])

  const loadMore = async () => {
    if (tree?.next_cursor == null || loadingMore) return
    setLoadingMore(true)
    setError(false)
    try {
      const result = await api.getSourceBrowserTree(sourceId, snapshotId, branch, folder, tree.next_cursor)
      setTree({ entries: [...tree.entries, ...result.entries], next_cursor: result.next_cursor })
    } catch {
      setError(true)
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <div className="source-browser-tree">
      {error && <p role="alert">{t('sourceBrowser.error')}</p>}
      {tree === null && !error && <p role="status">{t('sourceBrowser.loading')}</p>}
      {tree?.entries.length === 0 && <p role="status">{t('sourceBrowser.empty')}</p>}
      {tree && tree.entries.length > 0 && <ul>
        {tree.entries.map((entry) => <li key={`${entry.kind}:${entry.path}`} className={entry.kind === 'directory' ? 'resource-tree-row' : 'resource-item'}>
          <button type="button" className={entry.kind === 'directory' ? 'resource-tree-toggle' : 'resource-open'} aria-current={entry.path === file ? 'true' : undefined} onClick={() => (entry.kind === 'directory' ? onFolder : onFile)(entry.path)}>
            <span className="resource-file-icon" aria-hidden="true">{entry.kind === 'directory' ? '▸ 📁' : entry.name.includes('.') ? entry.name.split('.').at(-1)?.slice(0, 3).toUpperCase() : 'TXT'}</span>
            {entry.name}
          </button>
        </li>)}
      </ul>}
      {tree?.next_cursor != null && <button type="button" className="btn" disabled={loadingMore} onClick={() => void loadMore()}>{t('sourceBrowser.more')}</button>}
    </div>
  )
}

function SourceFile({ sourceId, snapshotId, branch, path, api, t }: SnapshotProps & { path: string }) {
  const titleId = useId()
  const [file, setFile] = useState<SourceBrowserFile | 'error' | null>(null)
  useEffect(() => {
    const request = new AbortController()
    api.getSourceBrowserFile(sourceId, snapshotId, branch, path, request.signal).then(
      (result) => { if (!request.signal.aborted) setFile(result) },
      () => { if (!request.signal.aborted) setFile('error') },
    )
    return () => request.abort()
  }, [sourceId, snapshotId, branch, path, api])

  return (
    <section className="knowledge-reader" aria-labelledby={titleId}>
      <div className="markdown-editor-heading">
        <div><h4 id={titleId}>{path}</h4><span className="badge">{t('sourceBrowser.readOnly')}</span></div>
      </div>
      {file === null && <p role="status">{t('sourceBrowser.loading')}</p>}
      {file === 'error' && <p role="alert">{t('sourceBrowser.error')}</p>}
      {file !== null && file !== 'error' && (file.status === 'ready'
        ? <pre className="markdown-preview source-code-preview" tabIndex={0} aria-label={path}><Suspense fallback={<code>{file.content}</code>}><HighlightedCode path={path} content={file.content ?? ''} /></Suspense></pre>
        : <p role="status">{t(`sourceBrowser.${file.status}`)}</p>)}
    </section>
  )
}
