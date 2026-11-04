export interface LastImport {
  status: string
  finished_at: string | null
}

export interface Source {
  id: number
  type: string
  name: string
  enabled: boolean
  last_import: LastImport | null
}

export type ConfigFieldKind = 'text' | 'path' | 'password'

export interface ConfigField {
  name: string
  label: string
  kind: ConfigFieldKind
  required: boolean
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
