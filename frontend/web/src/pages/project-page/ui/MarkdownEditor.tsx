import { useState } from 'react'
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
  onClose: () => void
}

export default function MarkdownEditor({ t, resource, content: initialContent, isMarkdown, candidates, onRead, onSave, onApprove, onClose }: Props) {
  const [content, setContent] = useState(initialContent)
  const [flowApproved, setFlowApproved] = useState(() => hasApprovedFlows(initialContent))
  const [mode, setMode] = useState<'preview' | 'edit'>('preview')
  const [mergeId, setMergeId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mergeNotice, setMergeNotice] = useState(false)

  const merge = async () => {
    const reference = candidates.find((candidate) => candidate.resource.id === mergeId)
    if (reference === undefined) return
    setBusy(true)
    setError(null)
    try {
      const otherContent = await onRead(reference)
      const current = content.trimEnd()
      const other = otherContent.trim()
      setContent(current && other ? `${current}\n\n---\n\n${other}\n` : `${current}${other}\n`)
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
      onClose()
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
      setFlowApproved(hasApprovedFlows(approvedContent))
      setMode('preview')
    } catch (approveError) {
      setError(approveError instanceof Error ? approveError.message : String(approveError))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay">
      <section className="modal markdown-editor" role="dialog" aria-modal="true" aria-labelledby="markdown-editor-title">
        <div className="markdown-editor-heading">
          <div><h2 id="markdown-editor-title">{resource.name}</h2><span className="badge">{t(isMarkdown ? 'materials.markdown' : 'materials.textFile')}</span></div>
          <button type="button" className="text-button" onClick={onClose} aria-label={t('common.cancel')}>×</button>
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
        {mode === 'preview' ? <pre className="markdown-preview">{content}</pre> : <textarea className="markdown-textarea" aria-label={t('materials.edit')} value={content} onChange={(event) => { setContent(event.target.value); setMergeNotice(false) }} />}
        {mergeNotice && <small className="success-note markdown-merge-notice">{t('materials.mergeDraftReady')}</small>}
        {error !== null && <p className="error" role="alert">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose}>{t('common.cancel')}</button>
          {onApprove !== undefined && !flowApproved && <button type="button" className="btn" onClick={() => void approve()} disabled={busy}>{t('project.approveUserFlow')}</button>}
          <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={busy}>{busy ? t('project.uploading') : t('materials.save')}</button>
        </div>
      </section>
    </div>
  )
}
