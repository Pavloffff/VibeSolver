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
}

export interface OllamaPullProgress {
  status: string
  progress?: number | null
  model_id?: string
  error?: string
}
