import { useState } from 'react'
import { useT } from '../../../shared/i18n'

interface Props {
  projectName: string
}

export default function IssuesPage({ projectName }: Props) {
  const { t } = useT()
  const [notice, setNotice] = useState<string | null>(null)

  return (
    <div className="issues-page">
      <div className="page-header">
        <div>
          <span className="eyebrow">{projectName}</span>
          <h1>{t('project.issues')}</h1>
          <p>{t('issues.pageDescription')}</p>
        </div>
        <button type="button" className="btn btn-primary btn-large" onClick={() => setNotice(t('project.issuesSoon'))}>
          <span aria-hidden="true">+</span>{t('project.addIssue')}
        </button>
      </div>
      <section className="project-card issues-page-empty">
        <div className="empty-state-icon"><span aria-hidden="true">＋</span></div>
        <h2>{t('project.noIssues')}</h2>
        <p>{t('issues.emptyDescription')}</p>
        {notice !== null && <p className="issues-notice" role="status">{notice}</p>}
      </section>
    </div>
  )
}
