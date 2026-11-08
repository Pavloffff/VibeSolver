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

function renderProject(api: ApiClient) {
  render(<I18nProvider><ProjectPage sourceId={1} api={api} onBack={() => {}} onOpenIssues={() => {}} /></I18nProvider>)
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
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
    } as unknown as ApiClient
    renderProject(api)

    expect(await screen.findByText('sample')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open on GitHub/ })).toHaveAttribute('href', project.config?.url)
    expect(screen.getByText('clone failed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start indexing' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Edit project' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'To issues' })).toBeInTheDocument()
  })

  it('adds an archive as a folder in project documentation', async () => {
    const updated = { ...project, config: { ...project.config, resources: { documentation: [{ id: 'guide-file', type: 'markdown', name: 'intro.md', path: 'guide/intro.md', config: { upload_key: 'uploads/guide-file' } }] } } }
    const api = {
      getSource: vi.fn().mockResolvedValueOnce(project).mockResolvedValueOnce(updated),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 12 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'done', progress: 100, error: null }),
      importLocalResource: vi.fn().mockResolvedValue({ added: ['guide/intro.md'], unchanged: [], conflicts: [] }),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
    } as unknown as ApiClient
    renderProject(api)
    const archive = new File(['docs'], 'guide.zip', { type: 'application/zip' })
    fireEvent.change((await screen.findAllByLabelText('Add a local file'))[0]!, { target: { files: [archive] } })

    await waitFor(() => expect(api.importLocalResource).toHaveBeenCalledWith(1, 'documentation', archive, '', 'uploaded'))
    expect(await screen.findByRole('button', { name: 'Expand guide' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start indexing' })).toBeDisabled()
  })

  it('opens and edits an extensionless text file from documentation', async () => {
    const withText = {
      ...project,
        config: { ...project.config, resources: { documentation: [{ id: 'license', type: 'file', name: 'LICENSE', path: 'LICENSE', config: { upload_key: 'uploads/license' } }] } },
    }
    const api = {
      getSource: vi.fn().mockResolvedValue(withText),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 12 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'done', progress: 100, error: null }),
      getResourceContent: vi.fn().mockResolvedValue({ content: 'hello' }),
      updateResourceContent: vi.fn().mockResolvedValue(undefined),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
    } as unknown as ApiClient
    renderProject(api)

    fireEvent.click(await screen.findByRole('button', { name: 'LICENSE: Open and edit' }))
    expect(await screen.findByText('Text file')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit text' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Edit text' }), { target: { value: 'updated' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(api.updateResourceContent).toHaveBeenCalledWith(1, 'documentation', 'license', 'updated'))
  })

  it('opens source code files from any programming language when marked as text', async () => {
    const withSource = {
      ...project,
      config: { ...project.config, resources: { documentation: [{ id: 'module', type: 'file', name: 'module.rs', path: 'module.rs', config: { upload_key: 'uploads/module', text: true, content_type: 'application/octet-stream' } }] } },
    }
    const api = {
      getSource: vi.fn().mockResolvedValue(withSource),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 12 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'done', progress: 100, error: null }),
      getResourceContent: vi.fn().mockResolvedValue({ content: 'fn main() {}' }),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
    } as unknown as ApiClient
    renderProject(api)

    fireEvent.click(await screen.findByRole('button', { name: 'module.rs: Open and edit' }))
    expect(await screen.findByText('Text file')).toBeInTheDocument()
    expect(api.getResourceContent).toHaveBeenCalledWith(1, 'documentation', 'module')
  })

  it('deletes a documentation folder and its contents after confirmation', async () => {
    const withFolder = {
      ...project,
      config: { ...project.config, resources: { documentation: [
        { id: 'readme', type: 'markdown', name: 'README.md', path: 'manual/README.md', config: { upload_key: 'uploads/readme' } },
        { id: 'setup', type: 'file', name: 'setup.txt', path: 'manual/install/setup.txt', config: { upload_key: 'uploads/setup', text: true } },
      ] } },
    }
    const api = {
      getSource: vi.fn().mockResolvedValue(withFolder),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 12 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'done', progress: 100, error: null }),
      deleteDocumentationFolder: vi.fn().mockResolvedValue(undefined),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
    } as unknown as ApiClient
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderProject(api)

    fireEvent.click(await screen.findByRole('button', { name: 'Expand manual' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete folder: manual' }))
    await waitFor(() => expect(api.deleteDocumentationFolder).toHaveBeenCalledWith(1, 'manual', 'documentation'))
    expect(confirm).toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('shows the Confluence placeholder without adding a fake resource', async () => {
    const api = {
      getSource: vi.fn().mockResolvedValue(project),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 12 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'done', progress: 100, error: null }),
      importLocalResource: vi.fn(),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
    } as unknown as ApiClient
    renderProject(api)

    fireEvent.click(await screen.findByRole('button', { name: 'Confluence' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Confluence connection is not available yet')
    expect(api.importLocalResource).not.toHaveBeenCalled()
  })
})
