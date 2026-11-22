import type { SolverGraph } from '../../../shared/api/types'
import { useT, type TranslationKey } from '../../../shared/i18n'

const labels: Record<string, [TranslationKey, TranslationKey]> = {
  triage: ['solver.triage', 'solver.triageHint'],
  investigate: ['solver.investigate', 'solver.investigateHint'],
  resolve: ['solver.resolve', 'solver.resolveHint'],
  answer: ['solver.answer', 'solver.answerHint'],
  escalate: ['solver.escalate', 'solver.escalateHint'],
}

export function useStepLabels() {
  const { t } = useT()
  return {
    label: (id: string) => labels[id] ? t(labels[id][0]) : id,
    description: (id: string) => labels[id] ? t(labels[id][1]) : '',
  }
}

function layout(graph: SolverGraph) {
  const depths = new Map<string, number>()
  const incoming = new Map(graph.nodes.map(node => [node.id, graph.edges.filter(edge => edge.target === node.id).map(edge => edge.source)]))
  for (let pass = 0; pass < graph.nodes.length; pass++) {
    for (const node of graph.nodes) {
      if (depths.has(node.id)) continue
      const parents = incoming.get(node.id) ?? []
      if (parents.every(parent => depths.has(parent))) {
        depths.set(node.id, Math.max(0, ...parents.map(parent => (depths.get(parent) ?? 0) + 1)))
      }
    }
  }
  const columns = Math.max(1, ...depths.values()) + 1
  const positions = new Map<string, { x: number, y: number }>()
  for (let column = 0; column < columns; column++) {
    const group = graph.nodes.filter(node => (depths.get(node.id) ?? 0) === column)
    group.forEach((node, index) => positions.set(node.id, {
      x: 11 + 78 * column / (columns - 1),
      y: 100 * (index + 1) / (group.length + 1),
    }))
  }
  return { positions, width: Math.min(23, 75 / columns) }
}

export default function FlowDiagram({ graph, selected, onSelect, enabled }: {
  graph: SolverGraph
  selected: string
  onSelect: (id: string) => void
  enabled: Record<string, boolean>
}) {
  const { t } = useT()
  const { label } = useStepLabels()
  const { positions, width } = layout(graph)
  return <div className="solver-map" role="group" aria-label={t('solver.flow')}>
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" className="solver-wires">
      {graph.edges.map(({ source, target }) => {
        const from = positions.get(source)
        const to = positions.get(target)
        if (!from || !to) return null
        const x1 = from.x + width / 2, x2 = to.x - width / 2
        const mid = (x1 + x2) / 2
        const bypass = to.x - from.x > 38
        const route = bypass
          ? `M ${from.x} ${from.y} V 86 H ${to.x} V ${to.y}`
          : `M ${x1} ${from.y} C ${mid} ${from.y} ${mid} ${to.y} ${x2} ${to.y}`
        return <path key={source + ':' + target} d={route} className={target === 'escalate' ? 'is-handoff' : ''} vectorEffect="non-scaling-stroke" />
      })}
    </svg>
    {graph.nodes.map(node => {
      const pos = positions.get(node.id)!
      const off = enabled[node.id] === false
      const terminal = !graph.edges.some(edge => edge.source === node.id)
      return <button key={node.id} type="button" className={`solver-node ${off ? 'is-off' : ''} ${terminal ? 'is-terminal' : ''}`}
        style={{ left: pos.x + '%', top: pos.y + '%', width: width + '%' }}
        aria-pressed={selected === node.id} onClick={() => onSelect(node.id)}>
        <span className="solver-node-status"><span aria-hidden="true" />{t(off ? 'solver.off' : terminal ? 'solver.conditional' : node.optional ? 'solver.on' : 'solver.required')}</span>
        <strong>{label(node.id)}</strong>
      </button>
    })}
  </div>
}
