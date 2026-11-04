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
  type: string
  name: string
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
