import { getApiBaseUrl } from '../config'
import { t } from '../i18n'
import { getLang } from '../state/settings'
import type {
  AvailableModel,
  ConnectorInfo,
  ImportStatus,
  ProjectIndexStatus,
  ProjectIndexType,
  ModelProvider,
  ModelProviderType,
  OllamaPullProgress,
  ProjectModelSelections,
  ProjectResource,
  ProjectStats,
  Source,
  WorkspaceModel,
} from './types'

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

  uploadMarkdown(file: File): Promise<{ upload_key: string }> {
    const form = new FormData()
    form.append('file', file)
    return this.request<{ upload_key: string }>('/api/v1/uploads/markdown', {
      method: 'POST',
      body: form,
      headers: {},
    })
  }

  importLocalResource(sourceId: number, category: string, file: File, parentPath = '', origin = 'uploaded'): Promise<{ added: string[]; unchanged: string[]; conflicts: { path: string; existing_id: string }[] }> {
    const form = new FormData()
    form.append('file', file)
    form.append('parent_path', parentPath)
    form.append('category', category)
    form.append('origin', origin)
    return this.request(`/api/v1/sources/${sourceId}/resources/import`, {
      method: 'POST',
      body: form,
      headers: {},
    })
  }

  deleteDocumentationFolder(sourceId: number, path: string, category = 'documentation'): Promise<void> {
    return this.request<void>(`/api/v1/sources/${sourceId}/resources/folder?path=${encodeURIComponent(path)}&category=${encodeURIComponent(category)}`, { method: 'DELETE' })
  }

  getResourceContent(sourceId: number, category: string, resourceId: string): Promise<{ content: string }> {
    return this.request<{ content: string }>(
      `/api/v1/sources/${sourceId}/resources/${encodeURIComponent(category)}/${encodeURIComponent(resourceId)}`,
    )
  }

  updateResourceContent(sourceId: number, category: string, resourceId: string, content: string): Promise<void> {
    return this.request<void>(
      `/api/v1/sources/${sourceId}/resources/${encodeURIComponent(category)}/${encodeURIComponent(resourceId)}`,
      { method: 'PATCH', body: JSON.stringify({ content }) },
    )
  }

  approveUserFlow(sourceId: number, resourceId: string): Promise<{ content: string }> {
    return this.request<{ content: string }>(
      `/api/v1/sources/${sourceId}/resources/user_flow/${encodeURIComponent(resourceId)}/approve`,
      { method: 'POST' },
    )
  }

  deleteResource(sourceId: number, category: string, resourceId: string): Promise<void> {
    return this.request<void>(
      `/api/v1/sources/${sourceId}/resources/${encodeURIComponent(category)}/${encodeURIComponent(resourceId)}`,
      { method: 'DELETE' },
    )
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

  getProjectIndexStatus(id: number): Promise<ProjectIndexStatus> {
    return this.request<ProjectIndexStatus>(`/api/v1/sources/${id}/indexes`)
  }

  startProjectIndexing(id: number, indexType: ProjectIndexType): Promise<{ run_id: number; task_id: string; status: string }> {
    return this.request(`/api/v1/sources/${id}/indexes/${indexType}`, { method: 'POST' })
  }

  generateProjectMaterials(id: number, category: 'documentation' | 'user_flow', instructions?: string): Promise<{ resources: ProjectResource[] }> {
    return this.request(`/api/v1/sources/${id}/materials/generate`, {
      method: 'POST',
      body: JSON.stringify({ category, ...(instructions === undefined ? {} : { instructions }) }),
    })
  }

  listModelProviderTypes(): Promise<ModelProviderType[]> {
    return this.request<ModelProviderType[]>('/api/v1/models/providers/catalog')
  }

  listModelProviders(): Promise<ModelProvider[]> {
    return this.request<ModelProvider[]>('/api/v1/models/providers')
  }

  testModelProvider(input: { provider_type: string; name: string; base_url?: string; api_key?: string }): Promise<{ status: string; available_models: number }> {
    return this.request('/api/v1/models/providers/test', { method: 'POST', body: JSON.stringify(input) })
  }

  createModelProvider(input: { provider_type: string; name: string; base_url?: string; api_key?: string }): Promise<ModelProvider> {
    return this.request<ModelProvider>('/api/v1/models/providers', { method: 'POST', body: JSON.stringify(input) })
  }

  updateModelProvider(id: number, input: { name: string; base_url?: string; api_key?: string }): Promise<ModelProvider> {
    return this.request<ModelProvider>(`/api/v1/models/providers/${id}`, { method: 'PATCH', body: JSON.stringify(input) })
  }

  testSavedModelProvider(id: number): Promise<{ status: string; available_models: number }> {
    return this.request<{ status: string; available_models: number }>(`/api/v1/models/providers/${id}/test`, { method: 'POST' })
  }

  deleteModelProvider(id: number): Promise<void> {
    return this.request<void>(`/api/v1/models/providers/${id}`, { method: 'DELETE' })
  }

  listWorkspaceModels(capability?: string): Promise<WorkspaceModel[]> {
    const query = capability ? `?capability=${encodeURIComponent(capability)}` : ''
    return this.request<WorkspaceModel[]>(`/api/v1/models${query}`)
  }

  listAvailableModels(providerId: number, capability?: string): Promise<AvailableModel[]> {
    const query = capability ? `?capability=${encodeURIComponent(capability)}` : ''
    return this.request<AvailableModel[]>(`/api/v1/models/providers/${providerId}/available${query}`)
  }

  syncProviderModels(providerId: number): Promise<WorkspaceModel[]> {
    return this.request<WorkspaceModel[]>(`/api/v1/models/providers/${providerId}/sync`, { method: 'POST' })
  }

  addProviderModel(providerId: number, providerModelId: string): Promise<WorkspaceModel> {
    return this.request<WorkspaceModel>(`/api/v1/models/providers/${providerId}/models`, {
      method: 'POST', body: JSON.stringify({ provider_model_id: providerModelId }),
    })
  }

  deleteWorkspaceModel(modelId: number): Promise<void> {
    return this.request<void>(`/api/v1/models/${modelId}`, { method: 'DELETE' })
  }

  async pullOllamaModel(
    providerId: number,
    modelId: string,
    onProgress: (event: OllamaPullProgress) => void,
    signal: AbortSignal,
  ): Promise<void> {
    let response: Response
    try {
      response = await fetch(`${this.getBaseUrl().replace(/\/+$/, '')}/api/v1/models/providers/${providerId}/models/pull`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId }),
        signal,
      })
    } catch (error) {
      if (signal.aborted) return
      throw new ApiError(0, t(getLang(), 'errors.serverUnavailable', { message: getErrorMessage(error) }))
    }
    if (!response.ok) {
      const body = await response.text()
      throw new ApiError(response.status, t(getLang(), 'errors.httpError', { status: String(response.status), body }))
    }
    if (response.body === null) throw new ApiError(response.status, t(getLang(), 'errors.invalidResponse'))
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.trim()) {
          const event = JSON.parse(line) as OllamaPullProgress
          onProgress(event)
          if (event.error) throw new ApiError(502, event.error)
        }
      }
      if (done) break
    }
    if (buffer.trim()) {
      const event = JSON.parse(buffer) as OllamaPullProgress
      onProgress(event)
      if (event.error) throw new ApiError(502, event.error)
    }
  }

  getProjectModelSelections(sourceId: number): Promise<ProjectModelSelections> {
    return this.request<ProjectModelSelections>(`/api/v1/models/projects/${sourceId}/selections`)
  }

  setProjectModelSelection(sourceId: number, role: string, modelId: number | null): Promise<ProjectModelSelections> {
    return this.request<ProjectModelSelections>(`/api/v1/models/projects/${sourceId}/selections/${encodeURIComponent(role)}`, {
      method: 'PUT', body: JSON.stringify({ model_id: modelId }),
    })
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
