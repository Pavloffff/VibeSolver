import type { ApiClient } from '../../../shared/api/client'
import type { DiagnosticTools, SolverProfile, SolverProfileInput } from '../../../shared/api/types'

type ApplyState<Input, Result> =
  | { status: 'idle' }
  | { status: 'saving'; input: Input }
  | { status: 'saved'; input: Input; result: Result }
  | { status: 'failed'; input: Input; error: unknown }

class ApplyQueue<Input, Result> {
  private state: ApplyState<Input, Result> = { status: 'idle' }
  private readonly listeners = new Set<() => void>()
  private pending?: { input: Input }
  private active: Promise<void> | null = null

  constructor(private readonly write: (input: Input) => Promise<Result>) {}

  getSnapshot = () => this.state
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  private publish(state: ApplyState<Input, Result>) {
    this.state = state
    this.listeners.forEach(listener => listener())
  }

  submit(input: Input) {
    this.pending = { input }
    this.publish({ status: 'saving', input })
    this.start()
  }

  retry = () => {
    if (this.state.status === 'failed') this.submit(this.state.input)
  }

  reset = () => {
    if (this.state.status !== 'saving') this.publish({ status: 'idle' })
  }

  async wait() {
    while (this.active !== null) await this.active
  }

  private start() {
    if (this.active !== null || this.pending === undefined) return
    this.active = this.drain().finally(() => {
      this.active = null
      this.start()
    })
  }

  private async drain() {
    while (this.pending !== undefined) {
      const { input } = this.pending
      this.pending = undefined
      try {
        const result = await this.write(input)
        if (this.pending === undefined) this.publish({ status: 'saved', input, result })
      } catch (error) {
        if (this.pending === undefined) this.publish({ status: 'failed', input, error })
      }
    }
  }
}

export type DiagnosticInput = Pick<DiagnosticTools, 'ui_probe' | 'web_provider' | 'allow_web_search'>

class ProjectApplyQueues {
  readonly create: ApplyQueue<SolverProfileInput, SolverProfile>
  readonly tools: ApplyQueue<DiagnosticInput, DiagnosticTools>
  selectedProfileId: number | null = null
  seenCreationId: number | null = null
  private readonly profiles = new Map<number, ApplyQueue<SolverProfileInput, SolverProfile>>()

  constructor(private readonly api: ApiClient, private readonly projectId: number) {
    this.create = new ApplyQueue(input => api.createSolverProfile(projectId, input))
    this.tools = new ApplyQueue(input => api.setDiagnosticTools(projectId, input))
  }

  profile(id: number) {
    const existing = this.profiles.get(id)
    if (existing !== undefined) return existing
    const queue = new ApplyQueue<SolverProfileInput, SolverProfile>(input => this.api.updateSolverProfile(this.projectId, id, input))
    this.profiles.set(id, queue)
    return queue
  }

  wait() {
    return Promise.all([this.create.wait(), this.tools.wait(), ...Array.from(this.profiles.values(), queue => queue.wait())])
  }
}

const queuesByClient = new WeakMap<ApiClient, Map<number, ProjectApplyQueues>>()

export function getApplyQueues(api: ApiClient, projectId: number) {
  let projects = queuesByClient.get(api)
  if (projects === undefined) {
    projects = new Map()
    queuesByClient.set(api, projects)
  }
  const existing = projects.get(projectId)
  if (existing !== undefined) return existing
  const queues = new ProjectApplyQueues(api, projectId)
  projects.set(projectId, queues)
  return queues
}
