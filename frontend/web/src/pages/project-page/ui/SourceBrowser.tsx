import { useEffect, useState } from 'react'
import type { ApiClient } from '../../../shared/api/client'
import type { SourceBrowserFile, SourceBrowserSnapshot, SourceBrowserTree } from '../../../shared/api/types'
import type { TranslationKey } from '../../../shared/i18n'
import './sourceBrowser.css'

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
    <section className="source-browser">
      <div className="source-browser-heading">
        <h3>{props.t('sourceBrowser.title')}</h3>
        <button type="button" className="btn" onClick={() => setRequest((current) => current + 1)}>
          {props.t(request === 0 ? 'sourceBrowser.open' : 'sourceBrowser.refresh')}
        </button>
      </div>
      {request > 0 && <SourceSnapshot key={`${props.sourceId}:${request}`} {...props} />}
    </section>
  )
}

function SourceSnapshot({ sourceId, api, t }: BrowserProps) {
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

  if (snapshot === null) return <p role="status">{t('sourceBrowser.loading')}</p>
  if (snapshot === 'error') return <p role="alert">{t('sourceBrowser.error')}</p>
  if (snapshot.status !== 'ready') return <p role="status">{t(`sourceBrowser.${snapshot.status}`)}</p>
  if (snapshot.snapshot_id === null) return <p role="alert">{t('sourceBrowser.error')}</p>

  const branch = selectedBranch ?? snapshot.branches[0] ?? ''
  return (
    <>
      {snapshot.branches.some(Boolean) && <label className="source-browser-branch">
        {t('sourceBrowser.branch')}
        <select value={branch} onChange={(event) => setSelectedBranch(event.target.value)}>
          {snapshot.branches.map((item) => <option key={item} value={item}>{item || t('sourceBrowser.noBranch')}</option>)}
        </select>
      </label>}
      <SourceBranch key={branch} sourceId={sourceId} snapshotId={snapshot.snapshot_id} branch={branch} api={api} t={t} />
    </>
  )
}

function SourceBranch(props: SnapshotProps) {
  const [folder, setFolder] = useState('')
  const [file, setFile] = useState<string | null>(null)
  const selectFolder = (path: string) => {
    setFolder(path)
    setFile(null)
  }
  const crumbs = folder ? folder.split('/') : []
  return (
    <>
      <div className="source-browser-crumbs">
        <button type="button" className="text-button" onClick={() => selectFolder('')}>{props.t('sourceBrowser.root')}</button>
        {crumbs.map((part, index) => {
          const path = crumbs.slice(0, index + 1).join('/')
          return <span key={path}><span aria-hidden="true"> / </span>
            <button type="button" className="text-button" onClick={() => selectFolder(path)}>{part}</button>
          </span>
        })}
      </div>
      <div className="source-browser-content">
        <SourceFolder key={folder} {...props} folder={folder} file={file} onFolder={selectFolder} onFile={setFile} />
        {file !== null && <SourceFile key={file} {...props} path={file} />}
      </div>
    </>
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
        {tree.entries.map((entry) => <li key={`${entry.kind}:${entry.path}`}>
          <button type="button" className="source-browser-entry" aria-current={entry.path === file ? 'true' : undefined} onClick={() => (entry.kind === 'directory' ? onFolder : onFile)(entry.path)}>
            <span className="source-browser-entry-icon" aria-hidden="true">{entry.kind === 'directory' ? '▸' : '·'}</span>
            {entry.name}
          </button>
        </li>)}
      </ul>}
      {tree?.next_cursor != null && <button type="button" className="btn" disabled={loadingMore} onClick={() => void loadMore()}>{t('sourceBrowser.more')}</button>}
    </div>
  )
}

function SourceFile({ sourceId, snapshotId, branch, path, api, t }: SnapshotProps & { path: string }) {
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
    <section className="source-browser-preview">
      <h4>{path}</h4>
      {file === null && <p role="status">{t('sourceBrowser.loading')}</p>}
      {file === 'error' && <p role="alert">{t('sourceBrowser.error')}</p>}
      {file !== null && file !== 'error' && (file.status === 'ready'
        ? <pre tabIndex={0} aria-label={path}><code>{file.content}</code></pre>
        : <p role="status">{t(`sourceBrowser.${file.status}`)}</p>)}
    </section>
  )
}
