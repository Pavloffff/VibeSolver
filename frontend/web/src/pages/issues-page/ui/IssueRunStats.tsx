import type { TicketDetail, TicketStep } from '../../../shared/api/types'
import { useT, type TranslationKey } from '../../../shared/i18n'

const USAGE_METRICS = [
  { field: 'tokens_in', label: 'issueWorkspace.ticketStatsInput' },
  { field: 'tokens_out', label: 'issueWorkspace.ticketStatsOutput' },
  { field: 'cost_usd', label: 'issueWorkspace.ticketStatsCost' },
] as const satisfies readonly { field: keyof TicketStep; label: TranslationKey }[]

export default function IssueRunStats({ detail }: { detail: TicketDetail }) {
  const { t, lang } = useT()
  const runs = detail.runs ?? []
  const runIds = new Set(runs.map(run => run.id))
  const unlinkedSteps = detail.steps.filter(step => step.run_id == null || !runIds.has(step.run_id)).length
  const modelSteps = detail.steps.filter(step => step.model_id != null || USAGE_METRICS.some(({ field }) => step[field] != null))
  const recordedTimes = detail.steps.filter(step =>
    step.duration_ms > 0 || (
      step.status !== 'skipped' && (step.model_id != null || (step.step !== 'answer' && step.step !== 'escalate'))
    ),
  )
  const durationMs = recordedTimes.reduce((total, step) => total + step.duration_ms, 0)
  const number = (value: number) => value.toLocaleString(lang)
  const currency = new Intl.NumberFormat(lang, { style: 'currency', currency: 'USD', maximumFractionDigits: 8 })
  const cost = (value: number) => value > 0 && value < 1e-8 ? `< ${currency.format(1e-8)}` : currency.format(value)

  return (
    <section className="issues-ticket-stats" aria-labelledby="issue-ticket-stats-heading">
      <h3 id="issue-ticket-stats-heading">{t('issueWorkspace.ticketStatsTitle')}</h3>
      {runs.length === 0 && detail.steps.length === 0 ? (
        <p className="resource-empty">{t('issueWorkspace.ticketStatsEmpty')}</p>
      ) : (
        <>
          <p className="field-hint">{t('issueWorkspace.ticketStatsScope')}</p>
          <dl className="issues-stats-grid issues-ticket-metrics">
            <div><dt>{t('issueWorkspace.ticketStatsRuns')}</dt><dd>{number(runs.length)}</dd></div>
            <div>
              <dt>{t('issueWorkspace.ticketStatsDuration')}</dt>
              <dd>{recordedTimes.length === 0 ? '—' : durationMs >= 1000
                ? (durationMs / 1000).toLocaleString(lang, { style: 'unit', unit: 'second', unitDisplay: 'short', maximumFractionDigits: 2 })
                : t('issues.duration', { value: number(durationMs) })}</dd>
            </div>
            {USAGE_METRICS.map(({ field, label }) => {
              const reported = modelSteps.flatMap(step => step[field] == null ? [] : [step[field]])
              const total = reported.reduce((sum, value) => sum + value, 0)
              return (
                <div key={field}>
                  <dt>{t(label)}</dt>
                  <dd>{reported.length === 0 ? '—' : field === 'cost_usd' ? cost(total) : number(total)}</dd>
                  {reported.length < modelSteps.length && (
                    <dd className="issues-ticket-metrics-coverage">{t('issueWorkspace.ticketStatsCoverage', {
                      reported: number(reported.length), total: number(modelSteps.length),
                    })}</dd>
                  )}
                </div>
              )
            })}
          </dl>
          {unlinkedSteps > 0 && <p className="field-hint">{t('issueWorkspace.ticketStatsLegacy', { count: number(unlinkedSteps) })}</p>}
        </>
      )}
    </section>
  )
}
