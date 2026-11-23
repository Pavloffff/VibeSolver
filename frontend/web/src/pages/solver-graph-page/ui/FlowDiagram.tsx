import { useId } from 'react'
import type { SolverGraph } from '../../../shared/api/types'
import { useT, type TranslationKey } from '../../../shared/i18n'
import type { layoutSolverGraph } from './solverLayout'

const labels: Record<string, [TranslationKey, TranslationKey]> = {
  log_intake: ['solver.logIntake', 'solver.logIntakeHint'],
  triage: ['solver.triage', 'solver.triageHint'],
  investigate: ['solver.investigate', 'solver.investigateHint'],
  read_code: ['solver.readCode', 'solver.readCodeHint'],
  recheck: ['solver.recheck', 'solver.recheckHint'],
  resolve: ['solver.resolve', 'solver.resolveHint'],
  answer: ['solver.answer', 'solver.answerHint'],
  escalate: ['solver.escalate', 'solver.escalateHint'],
  flow: ['solver.flowAgent', 'solver.flowAgentHint'],
  logs: ['solver.logsAgent', 'solver.logsAgentHint'],
  code: ['solver.codeAgent', 'solver.codeAgentHint'],
  ui: ['solver.uiAgent', 'solver.uiAgentHint'],
  web: ['solver.webAgent', 'solver.webAgentHint'],
  review: ['solver.reviewAgent', 'solver.reviewAgentHint'],
}

export function useStepLabels() {
  const { t } = useT()
  return {
    label: (id: string) => labels[id] ? t(labels[id][0]) : id,
    description: (id: string) => labels[id] ? t(labels[id][1]) : '',
  }
}

type Connection = ReturnType<typeof layoutSolverGraph>['connections'][number]

export function SolverRoutes({ routes }: { routes: Connection[] }) {
  const { t } = useT()
  const { label } = useStepLabels()
  return <ul className="solver-route-list">
    {routes.map((route, index) => (
      <li key={index}>{t(route.feedback ? 'solver.returnToStep' : 'solver.goToStep', { step: label(route.target) })}</li>
    ))}
  </ul>
}

export default function FlowDiagram({ graph, layout, selected, onSelect, enabled }: {
  graph: SolverGraph
  layout: ReturnType<typeof layoutSolverGraph>
  selected: string
  onSelect: (id: string) => void
  enabled: Record<string, boolean | undefined>
}) {
  const { t } = useT()
  const { label } = useStepLabels()
  const marker = useId()
  const { nodes, connections, width, height, cardWidth, cardHeight } = layout
  const showFeedback = connections.some(route => route.feedback)
  return <>
    {showFeedback && <p className="solver-map-legend"><span aria-hidden="true" />{t('solver.feedbackLegend')}</p>}
    <div className="solver-map-scroll" tabIndex={0} role="group" aria-label={t('solver.flow')}>
      <div className="solver-map" style={{ width, height }}>
        <svg viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className="solver-wires">
          <defs>
            <marker id={marker} markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto" markerUnits="userSpaceOnUse">
              <path className="solver-arrow" d="M 1 1 L 7 4 L 1 7" />
            </marker>
          </defs>
          {connections.map(({ source, target, path, feedback }, index) => (
            <path
              key={index}
              data-source={source}
              data-target={target}
              d={path}
              markerEnd={`url(#${marker})`}
              className={feedback ? 'is-feedback' : undefined}
            />
          ))}
        </svg>
        {graph.nodes.map(node => {
          const pos = nodes.get(node.id)!
          const outgoing = connections.filter(route => route.source === node.id)
          const off = node.optional && enabled[node.id] !== true
          const terminal = outgoing.length === 0
          return <div key={node.id} className="solver-map-entry" style={{ left: pos.x, top: pos.y, width: cardWidth, minHeight: cardHeight }}>
            <button type="button" className={`solver-node ${off ? 'is-off' : ''} ${terminal ? 'is-terminal' : ''}`}
              style={{ minHeight: cardHeight }}
              aria-pressed={selected === node.id} onClick={() => onSelect(node.id)}>
              <span className="solver-node-status"><span aria-hidden="true" />{t(off ? 'solver.off' : terminal ? 'solver.conditional' : node.optional ? 'solver.on' : 'solver.required')}</span>
              <strong>{label(node.id)}</strong>
            </button>
            {outgoing.length > 0 && <div className="solver-mobile-routes"><SolverRoutes routes={outgoing} /></div>}
          </div>
        })}
      </div>
    </div>
  </>
}
