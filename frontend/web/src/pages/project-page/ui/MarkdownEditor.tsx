import { useId, useState } from 'react'
import type { ProjectResource } from '../../../shared/api/types'
import type { TranslationKey } from '../../../shared/i18n'

type Translate = (key: TranslationKey) => string
type ResourceCategory = 'documentation' | 'user_flow'

function hasApprovedFlows(content: string): boolean {
  try {
    const parsed: unknown = JSON.parse(content)
    const flows: unknown[] = Array.isArray(parsed) ? parsed : [parsed]
    return flows.length > 0 && flows.every((flow) => typeof flow === 'object' && flow !== null && 'approved' in flow && flow.approved === true)
  } catch {
    return false
  }
}

export interface MarkdownResourceReference {
  category: ResourceCategory
  resource: ProjectResource
}

interface Props {
  t: Translate
  resource: ProjectResource
  content: string
  isMarkdown: boolean
  candidates: MarkdownResourceReference[]
  onRead: (reference: MarkdownResourceReference) => Promise<string>
  onSave: (content: string) => Promise<void>
  onApprove?: () => Promise<string>
  onDirtyChange: (dirty: boolean) => void
  onClose: () => void
}

export default function MarkdownEditor({ t, resource, content: initialContent, isMarkdown, candidates, onRead, onSave, onApprove, onDirtyChange, onClose }: Props) {
  const titleId = useId()
  const [content, setContent] = useState(initialContent)
  const [savedContent, setSavedContent] = useState(initialContent)
  const [flowApproved, setFlowApproved] = useState(() => hasApprovedFlows(initialContent))
  const [mode, setMode] = useState<'preview' | 'edit'>('preview')
  const [mergeId, setMergeId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mergeNotice, setMergeNotice] = useState(false)
  const hasChanges = content !== savedContent
  const canApprove = onApprove !== undefined && !flowApproved

  const updateDraft = (draft: string) => {
    setContent(draft)
    onDirtyChange(draft !== savedContent)
  }

  const merge = async () => {
    const reference = candidates.find((candidate) => candidate.resource.id === mergeId)
    if (reference === undefined) return
    setBusy(true)
    setError(null)
    try {
      const otherContent = await onRead(reference)
      const current = content.trimEnd()
      const other = otherContent.trim()
      updateDraft(current && other ? `${current}\n\n---\n\n${other}\n` : `${current}${other}\n`)
      setMergeNotice(true)
      setMode('edit')
    } catch (mergeError) {
      setError(mergeError instanceof Error ? mergeError.message : String(mergeError))
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await onSave(content)
      setSavedContent(content)
      onDirtyChange(false)
      setMode('preview')
      setFlowApproved(hasApprovedFlows(content))
      setMergeNotice(false)
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : String(saveError))
    } finally {
      setBusy(false)
    }
  }

  const approve = async () => {
    setBusy(true)
    setError(null)
    try {
      const approvedContent = await onApprove?.() ?? content
      setContent(approvedContent)
      setSavedContent(approvedContent)
      onDirtyChange(false)
      setFlowApproved(hasApprovedFlows(approvedContent))
      setMode('preview')
    } catch (approveError) {
      setError(approveError instanceof Error ? approveError.message : String(approveError))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="knowledge-reader markdown-editor" aria-labelledby={titleId}>
      <div className="markdown-editor-heading">
        <div><h4 id={titleId}>{resource.path ?? resource.name}</h4><span className="badge">{t(isMarkdown ? 'materials.markdown' : 'materials.textFile')}</span></div>
      </div>
      <div className="markdown-editor-toolbar">
        <div className="markdown-editor-modes">
          <button type="button" className={mode === 'preview' ? 'btn btn-selected' : 'btn'} onClick={() => setMode('preview')}>{t('materials.preview')}</button>
          <button type="button" className={mode === 'edit' ? 'btn btn-selected' : 'btn'} onClick={() => setMode('edit')}>{t('materials.edit')}</button>
        </div>
        <div className="markdown-merge-controls">
          {isMarkdown && <select aria-label={t('materials.mergeWith')} value={mergeId} onChange={(event) => setMergeId(event.target.value)}>
            <option value="">{t('materials.selectMergeSource')}</option>
            {candidates.map(({ category, resource: candidate }) => <option key={`${category}-${candidate.id}`} value={candidate.id}>{candidate.name}</option>)}
          </select>}
          {isMarkdown && <button type="button" className="btn" onClick={() => void merge()} disabled={!mergeId || busy}>{t('materials.merge')}</button>}
        </div>
      </div>
      {mode === 'preview' ? <pre className="markdown-preview">{content}</pre> : <textarea className="markdown-textarea" aria-label={t('materials.edit')} value={content} disabled={busy} onChange={(event) => { updateDraft(event.target.value); setMergeNotice(false) }} />}
      {mergeNotice && <small className="success-note markdown-merge-notice">{t('materials.mergeDraftReady')}</small>}
      {error !== null && <p className="error" role="alert">{error}</p>}
      {(mode === 'edit' || hasChanges || canApprove) && (
        <div className="modal-actions">
          {(mode === 'edit' || hasChanges) && <button type="button" className="btn" disabled={busy} onClick={onClose}>{t('common.cancel')}</button>}
          {canApprove && <button type="button" className="btn" onClick={() => void approve()} disabled={busy || hasChanges}>{t('project.approveUserFlow')}</button>}
          {(mode === 'edit' || hasChanges) && <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={busy}>{busy ? t('project.uploading') : t('materials.save')}</button>}
        </div>
      )}
    </section>
  )
}
