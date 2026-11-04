import { getApiBaseUrl } from '../config'
import { t } from '../i18n'
import { getLang } from '../state/settings'
import type { ConnectorInfo, ImportStatus, ProjectResource, ProjectStats, Source } from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

export class ApiClient {
  private readonly getBaseUrl: () => string

  constructor(getBaseUrl: () => string) {
    this.getBaseUrl = getBaseUrl
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response
    try {
      response = await fetch(this.getBaseUrl().replace(/\/+$/, '') + path, {
        headers: { 'Content-Type': 'application/json' },
        ...init,
      })
    } catch (error) {
      throw new ApiError(0, t(getLang(), 'errors.serverUnavailable', { message: getErrorMessage(error) }))
    }
    if (!response.ok) {
      const body = await response.text()
      throw new ApiError(
        response.status,
        t(getLang(), 'errors.httpError', { status: String(response.status), body }),
      )
    }
    const body = await response.text()
    if (!body) {
      return undefined as T
    }
    try {
      return JSON.parse(body) as T
    } catch {
      throw new ApiError(response.status, t(getLang(), 'errors.invalidResponse'))
    }
  }

  listSources(): Promise<Source[]> {
    return this.request<Source[]>('/api/v1/sources')
  }

  getSource(id: number): Promise<Source> {
    return this.request<Source>(`/api/v1/sources/${id}`)
  }

  getProjectStats(id: number): Promise<ProjectStats> {
    return this.request<ProjectStats>(`/api/v1/sources/${id}/stats`)
  }

  updateSource(
    id: number,
    name: string,
    config: Record<string, string>,
    resources?: Record<string, ProjectResource[]>,
  ): Promise<Source> {
    return this.request<Source>(`/api/v1/sources/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name, config, ...(resources === undefined ? {} : { resources }) }),
    })
  }

  createSource(type: string, name: string, config: Record<string, string>): Promise<Source> {
    return this.request<Source>('/api/v1/sources', {
      method: 'POST',
      body: JSON.stringify({ type, name, config }),
    })
  }

  uploadArchive(file: File): Promise<{ upload_key: string }> {
    const form = new FormData()
    form.append('file', file)
    return this.request<{ upload_key: string }>('/api/v1/uploads', {
      method: 'POST',
      body: form,
      headers: {},
    })
  }

  deleteSource(id: number): Promise<void> {
    return this.request<void>(`/api/v1/sources/${id}`, { method: 'DELETE' })
  }

  listConnectors(): Promise<ConnectorInfo[]> {
    return this.request<ConnectorInfo[]>('/api/v1/connectors')
  }

  startImport(id: number): Promise<{ task_id: string }> {
    return this.request<{ task_id: string }>(`/api/v1/sources/${id}/import`, { method: 'POST' })
  }

  getImportStatus(id: number): Promise<ImportStatus> {
    return this.request<ImportStatus>(`/api/v1/sources/${id}/import`)
  }

  async checkHealth(): Promise<void> {
    await this.request<unknown>('/health')
  }
}

let singleton: ApiClient | null = null

export function getApiClient(): ApiClient {
  if (!singleton) {
    singleton = new ApiClient(getApiBaseUrl)
  }
  return singleton
}
