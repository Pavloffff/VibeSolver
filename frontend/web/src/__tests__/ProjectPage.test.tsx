import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ApiClient } from '../shared/api/client'
import type { Source } from '../shared/api/types'
import ProjectPage from '../pages/project-page'
import { I18nProvider } from '../shared/i18n'

const project: Source = {
  id: 1,
  type: 'git',
  name: 'sample',
  enabled: true,
  config: { url: 'https://github.com/acme/sample.git' },
  last_import: null,
}

const connectors = [{
  type: 'git',
  ready: true,
  config_schema: { fields: [{ name: 'url', label: 'URL', kind: 'text' as const, required: true }] },
}]

function renderProject(api: ApiClient) {
  render(<I18nProvider><ProjectPage sourceId={1} api={api} onBack={() => {}} /></I18nProvider>)
}

beforeEach(() => {
  localStorage.setItem('vibesolver.lang', 'en')
})

describe('ProjectPage', () => {
  it('shows project import status, file stats, GitHub link and disabled index action', async () => {
    const api = {
      getSource: vi.fn().mockResolvedValue(project),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 12 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'failed', progress: 0, error: 'clone failed' }),
      startImport: vi.fn(),
    } as unknown as ApiClient
    renderProject(api)

    expect(await screen.findByText('sample')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open on GitHub/ })).toHaveAttribute('href', project.config?.url)
    expect(screen.getByText('clone failed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start indexing' })).toBeDisabled()
    expect(screen.getAllByRole('button', { name: 'Edit project' })).toHaveLength(2)
  })

  it('adds an archive as project documentation', async () => {
    const updated = { ...project, config: { ...project.config, resources: { documentation: [{ type: 'archive', name: 'guide.zip', config: { upload_key: 'uploads/guide' } }] } } }
    const api = {
      getSource: vi.fn().mockResolvedValue(project),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 12 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'done', progress: 100, error: null }),
      uploadArchive: vi.fn().mockResolvedValue({ upload_key: 'uploads/guide' }),
      updateSource: vi.fn().mockResolvedValue(updated),
    } as unknown as ApiClient
    renderProject(api)
    const archive = new File(['docs'], 'guide.zip', { type: 'application/zip' })
    fireEvent.change(await screen.findByLabelText(/Add documentation/), { target: { files: [archive] } })

    await waitFor(() => expect(api.uploadArchive).toHaveBeenCalledWith(archive))
    await waitFor(() => expect(api.updateSource).toHaveBeenCalledWith(1, 'sample', {}, {
      documentation: [{ type: 'archive', name: 'guide.zip', config: { upload_key: 'uploads/guide' } }],
    }))
    expect(await screen.findByText('guide.zip')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start indexing' })).toBeEnabled()
  })

  it('saves edited connector settings and queues a replacement import', async () => {
    const updated = { ...project, name: 'fixed repo', config: { url: 'https://github.com/acme/fixed.git' } }
    const api = {
      getSource: vi.fn().mockResolvedValue(project),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 0 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'failed', progress: 0, error: 'clone failed' }),
      listConnectors: vi.fn().mockResolvedValue(connectors),
      updateSource: vi.fn().mockResolvedValue(updated),
      startImport: vi.fn().mockResolvedValue({ task_id: 'retry-1' }),
    } as unknown as ApiClient
    renderProject(api)
    fireEvent.click((await screen.findAllByRole('button', { name: 'Edit project' }))[0]!)
    fireEvent.change(await screen.findByLabelText('URL *'), { target: { value: 'https://github.com/acme/fixed.git' } })
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'fixed repo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save and re-import' }))

    await waitFor(() => expect(api.updateSource).toHaveBeenCalledWith(1, 'fixed repo', {
      url: 'https://github.com/acme/fixed.git',
    }))
    expect(api.startImport).toHaveBeenCalledWith(1)
  })
})
