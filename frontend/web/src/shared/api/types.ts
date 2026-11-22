export interface LastImport {
  status: string
  finished_at: string | null
}

export interface Source {
  id: number
  type: string
  name: string
  enabled: boolean
  config?: Record<string, unknown>
  last_import: LastImport | null
}

export interface ProjectResource {
  id?: string
  type: string
  name: string
  path?: string
  config: Record<string, unknown>
}

export interface ProjectStats {
  file_count: number
}

export type ConfigFieldKind = 'text' | 'path' | 'password' | 'folder' | 'file'

export interface ConfigField {
  name: string
  label: string
  kind: ConfigFieldKind
  required: boolean
  hint?: string | null
  placeholder?: string | null
}

export interface ConfigSchema {
  fields: ConfigField[]
}

export interface ConnectorInfo {
  type: string
  ready: boolean
  config_schema: ConfigSchema
}

export type ImportState = 'pending' | 'running' | 'done' | 'failed'

export interface ImportStatus {
  status: ImportState
  progress: number
  error: string | null
}

export type ProjectIndexType = 'code' | 'documentation' | 'user_flow'
export type ProjectIndexState = 'not_started' | 'queued' | 'running' | 'completed' | 'failed' | 'stale'

export interface ProjectIndexRun {
  index_type: ProjectIndexType
  status: ProjectIndexState
  progress: number
  run_id: number | null
  snapshot_id: number | null
  files_total: number
  chunks_total: number
  error: string | null
  updated_at: string | null
}

export interface ProjectIndexStatus {
  ready: boolean
  import_status: string
  indexes: ProjectIndexRun[]
}

export interface ModelProviderType {
  provider_type: string
  display_name: string
  default_url: string
  requires_api_key: boolean
  fixed_url: boolean
  sync_all_models: boolean
  supports_model_pull: boolean
}

export interface ModelProvider {
  id: number
  provider_type: string
  name: string
  base_url: string
  has_api_key: boolean
}

export interface WorkspaceModel {
  id: number
  provider_connection_id: number
  provider_type: string
  provider_name: string
  provider_model_id: string
  display_name: string
  capabilities: string[]
  status: string
  progress: number | null
  metadata: Record<string, unknown>
}

export interface AvailableModel {
  provider_model_id: string
  display_name: string
  capabilities: string[]
  status: string
  metadata: Record<string, unknown>
}

export interface ProjectModelSelections {
  indexing: number | null
  documentation_generation: number | null
  ticket_resolution?: number | null
  ticket_triage?: number | null
  ticket_resolution_cheap?: number | null
}

export interface TicketStats {
  total: number
  by_status: Record<string, number>
  completed: number
  autoresolve_rate: number
  tokens_in: number
  tokens_out: number
  cost_usd: number | null
  avg_cost_usd: number | null
  avg_tokens_per_ticket: number
}

export interface TicketBrief {
  id: number
  title: string
  status: string
  created_at: string | null
  has_unready_log_attachments?: boolean
}

export interface TicketCitation {
  source_ref: string
  path: string
  index_type: string
  start_line: number | null
  end_line: number | null
}

export interface Ticket {
  id: number
  source_id: number
  title: string
  description: string
  status: string
  triage: Record<string, unknown> | null
  answer: string | null
  escalate_reason: string | null
  citations: TicketCitation[]
  created_at: string | null
  updated_at: string | null
}

export interface TicketStep {
  step: string
  input_data: Record<string, unknown>
  output_data: Record<string, unknown>
  model_id: number | null
  duration_ms: number
  tokens_in: number | null
  tokens_out: number | null
  cost_usd: number | null
  created_at: string | null
}

export interface TicketDetail {
  ticket: Ticket
  steps: TicketStep[]
}

export type TicketLogAttachmentStatus = 'queued' | 'processing' | 'ready' | 'failed'

export interface TicketLogAttachment {
  id: number
  filename: string
  size_bytes: number
  status: TicketLogAttachmentStatus
  error: string | null
  created_at: string | null
  updated_at: string | null
}

export interface OllamaPullProgress {
  status: string
  progress?: number | null
  model_id?: string
  error?: string
}
