import type { SolverGraph } from '../../../shared/api/types'

type Edge = SolverGraph['edges'][number]

const CARD_WIDTH = 156
const CARD_HEIGHT = 88
const COLUMN_GAP = 52
const ROW_GAP = 26
const PADDING = 18
const LANE_GAP = 15
const PORT_GAP = 13

export function layoutSolverGraph(graph: SolverGraph) {
  const outgoing = new Map<string, Edge[]>(graph.nodes.map(node => [node.id, []]))
  const edges = graph.edges.filter(({ source, target }) => outgoing.has(source) && outgoing.has(target))
  for (const edge of edges) outgoing.get(edge.source)!.push(edge)
  const nodeOrder = new Map(graph.nodes.map(({ id }, index) => [id, index]))
  for (const targets of outgoing.values()) {
    targets.sort((edge, other) => nodeOrder.get(edge.target)! - nodeOrder.get(other.target)!)
  }

  const feedback = new Set<Edge>()
  const visiting = new Set<string>()
  const finished = new Set<string>()
  const reverseOrder: string[] = []
  function visit(id: string) {
    visiting.add(id)
    for (const edge of outgoing.get(id) ?? []) {
      if (visiting.has(edge.target)) feedback.add(edge)
      else if (!finished.has(edge.target)) visit(edge.target)
    }
    visiting.delete(id)
    finished.add(id)
    reverseOrder.push(id)
  }
  for (const node of graph.nodes) {
    if (!finished.has(node.id)) visit(node.id)
  }

  const ranks = new Map(graph.nodes.map(node => [node.id, 0]))
  for (const id of reverseOrder.reverse()) {
    for (const edge of outgoing.get(id) ?? []) {
      if (!feedback.has(edge)) ranks.set(edge.target, Math.max(ranks.get(edge.target)!, ranks.get(id)! + 1))
    }
  }
  const columns = Array.from({ length: Math.max(0, ...ranks.values()) + 1 }, () => [] as string[])
  for (const { id } of graph.nodes) columns[ranks.get(id)!]!.push(id)
  const spanning = edges.filter(edge => !feedback.has(edge) && ranks.get(edge.target)! - ranks.get(edge.source)! > 1)
  const gridTop = PADDING + spanning.length * LANE_GAP
  const maxRows = Math.max(1, ...columns.map(column => column.length))
  const gridHeight = maxRows * CARD_HEIGHT + (maxRows - 1) * ROW_GAP
  const nodes = new Map<string, { x: number; y: number }>()
  columns.forEach((column, rank) => {
    const columnHeight = column.length * CARD_HEIGHT + (column.length - 1) * ROW_GAP
    column.forEach((id, index) => nodes.set(id, {
      x: PADDING + COLUMN_GAP / 2 + rank * (CARD_WIDTH + COLUMN_GAP),
      y: gridTop + (gridHeight - columnHeight) / 2 + index * (CARD_HEIGHT + ROW_GAP),
    }))
  })

  let upperLane = 0
  let lowerLane = 0
  const connections = edges.map(edge => {
    const from = nodes.get(edge.source)!
    const to = nodes.get(edge.target)!
    const x1 = from.x + CARD_WIDTH
    const x2 = to.x
    const y1 = from.y + CARD_HEIGHT / 2
    const y2 = to.y + CARD_HEIGHT / 2
    const isFeedback = feedback.has(edge)
    const spansColumns = ranks.get(edge.target)! - ranks.get(edge.source)! > 1
    if (isFeedback || spansColumns) {
      const lane = isFeedback
        ? gridTop + gridHeight + ++lowerLane * LANE_GAP
        : gridTop - ++upperLane * LANE_GAP
      const path = `M ${x1} ${y1} H ${x1 + PORT_GAP} V ${lane} H ${x2 - PORT_GAP} V ${y2} H ${x2}`
      return { ...edge, path, feedback: isFeedback }
    }
    const mid = (x1 + x2) / 2
    return { ...edge, path: `M ${x1} ${y1} C ${mid} ${y1} ${mid} ${y2} ${x2} ${y2}`, feedback: false }
  })

  return {
    nodes, connections, cardWidth: CARD_WIDTH, cardHeight: CARD_HEIGHT,
    width: 2 * PADDING + columns.length * (CARD_WIDTH + COLUMN_GAP),
    height: gridTop + gridHeight + lowerLane * LANE_GAP + PADDING,
  }
}
