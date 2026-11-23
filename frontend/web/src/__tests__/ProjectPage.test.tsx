import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

function renderProject(api: ApiClient, experimental = false) {
  return render(<I18nProvider><ProjectPage sourceId={1} api={api} experimental={experimental} onBack={() => {}} /></I18nProvider>)
}

const indexStatus = {
  ready: false,
  indexes: [
    { index_type: 'code', status: 'not_started', progress: 0, run_id: null, snapshot_id: null, files_total: 0, chunks_total: 0, error: null, updated_at: null },
    { index_type: 'documentation', status: 'not_started', progress: 0, run_id: null, snapshot_id: null, files_total: 0, chunks_total: 0, error: null, updated_at: null },
    { index_type: 'user_flow', status: 'not_started', progress: 0, run_id: null, snapshot_id: null, files_total: 0, chunks_total: 0, error: null, updated_at: null },
  ],
}

beforeEach(() => {
  localStorage.setItem('vibesolver.lang', 'en')
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () { this.open = true }
    HTMLDialogElement.prototype.close = function () { this.open = false }
  }
})

describe('ProjectPage', () => {
  it.each([
    { locale: 'en', context: 'Knowledge sources', archive: 'Project archive', flow: 'User Flow', fileCount: 'User Flow files', emptyFlow: 'No User Flow descriptions attached yet.', generate: 'Generate User Flow from docs', code: 'Source code', branch: 'Branch', readOnly: 'Read only' },
    { locale: 'ru', context: 'Источники знаний', archive: 'Архив проекта', flow: 'Пользовательские сценарии', fileCount: 'Файлы пользовательских сценариев', emptyFlow: 'Пользовательские сценарии пока не добавлены.', generate: 'Сгенерировать пользовательские сценарии из документации', code: 'Исходный код', branch: 'Ветка', readOnly: 'Только чтение' },
    { locale: 'zh', context: '知识来源', archive: '项目压缩包', flow: '用户流程', fileCount: '用户流程文件', emptyFlow: '尚未添加用户流程。', generate: '从文档生成用户流程', code: '源代码', branch: '分支', readOnly: '只读' },
  ])('localizes project, user flow and source UI in $locale while preserving raw data', async ({ locale, context, archive, flow, fileCount, emptyFlow, generate, code, branch, readOnly }) => {
    localStorage.setItem('vibesolver.lang', locale)
    const content = 'static source Содержимое 目录'
    const api = {
      getSource: vi.fn().mockResolvedValue({ ...project, type: 'archive' }),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 12345 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'failed', progress: 0, error: 'clone failed: src/main.py' }),
      getProjectIndexStatus: vi.fn().mockResolvedValue(indexStatus),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getSourceBrowserSnapshot: vi.fn().mockResolvedValue({ status: 'ready', snapshot_id: 8, branches: ['feature/backend'] }),
      getSourceBrowserTree: vi.fn().mockResolvedValue({
        entries: [{ kind: 'file', name: 'raw.txt', path: 'raw.txt', size_bytes: 30 }],
        next_cursor: null,
      }),
      getSourceBrowserFile: vi.fn().mockResolvedValue({ status: 'ready', path: 'raw.txt', content }),
    } as unknown as ApiClient
    renderProject(api, true)
    expect(await screen.findByText(fileCount)).toBeInTheDocument()
    expect(screen.getByText(archive)).toHaveClass('badge')
    expect(screen.getByText((_, element) => element?.textContent === new Intl.NumberFormat(locale).format(12345), { selector: 'strong' })).toBeInTheDocument()
    expect(await screen.findByText('clone failed: src/main.py')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: flow }))
    const workspace = screen.getByRole('dialog', { name: context })
    expect(within(workspace).getByText(emptyFlow)).toBeVisible()
    expect(within(workspace).getByRole('button', { name: generate })).toBeDisabled()
    fireEvent.click(within(workspace).getByRole('button', { name: code }))
    expect(await within(workspace).findByRole('combobox', { name: branch })).toHaveValue('feature/backend')
    fireEvent.click(await within(workspace).findByRole('button', { name: 'raw.txt' }))
    expect(await within(workspace).findByText(readOnly)).toBeInTheDocument()
    expect(await within(workspace).findByText(content)).toBeInTheDocument()
  })

  it('shows project import status, file stats, GitHub link and disabled index action', async () => {
    const api = {
      getSource: vi.fn().mockResolvedValue(project),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 12 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'failed', progress: 0, error: 'clone failed' }),
      startImport: vi.fn(),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      getProjectIndexStatus: vi.fn().mockResolvedValue(indexStatus),
    } as unknown as ApiClient
    renderProject(api)

    expect(await screen.findByText('sample')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open on GitHub/ })).toHaveAttribute('href', project.config?.url)
    expect(screen.getByText('clone failed')).toBeInTheDocument()
    const startButtons = screen.getAllByRole('button', { name: 'Start indexing' })
    expect(startButtons).toHaveLength(3)
    for (const button of startButtons) expect(button).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Edit project' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'To issues' })).not.toBeInTheDocument()
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
      getProjectIndexStatus: vi.fn().mockResolvedValue(indexStatus),
    } as unknown as ApiClient
    renderProject(api)
    fireEvent.click(await screen.findByRole('button', { name: 'Open knowledge workspace' }))
    const archive = new File(['docs'], 'guide.zip', { type: 'application/zip' })
    fireEvent.change((await screen.findAllByLabelText('Add a local file'))[0]!, { target: { files: [archive] } })

    await waitFor(() => expect(api.importLocalResource).toHaveBeenCalledWith(1, 'documentation', archive, '', 'uploaded'))
    expect(await screen.findByRole('button', { name: 'Expand guide' })).toBeInTheDocument()
    for (const button of screen.getAllByRole('button', { name: 'Start indexing' })) expect(button).toBeDisabled()
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
      getProjectIndexStatus: vi.fn().mockResolvedValue(indexStatus),
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
      getProjectIndexStatus: vi.fn().mockResolvedValue(indexStatus),
    } as unknown as ApiClient
    renderProject(api)

    fireEvent.click(await screen.findByRole('button', { name: 'module.rs: Open and edit' }))
    expect(await screen.findByText('Text file')).toBeInTheDocument()
    expect(api.getResourceContent).toHaveBeenCalledWith(1, 'documentation', 'module')
  })

  it('opens a full viewport workspace directly from a file and preserves drafts and focus on exit', async () => {
    const withResources = {
      ...project,
      config: { resources: {
        documentation: [{ id: 'doc', type: 'markdown', name: 'README.md', config: {} }],
        user_flow: [{ id: 'flow', type: 'file', name: 'checkout.json', config: { text: true } }],
      } },
    }
    const api = {
      getSource: vi.fn().mockResolvedValue(withResources),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 2 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'done', progress: 100, error: null }),
      getProjectIndexStatus: vi.fn().mockResolvedValue(indexStatus),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getResourceContent: vi.fn().mockResolvedValue({ content: '{}' }),
      updateResourceContent: vi.fn().mockResolvedValue(undefined),
    } as unknown as ApiClient
    renderProject(api)

    const shortcut = await screen.findByRole('button', { name: 'README.md: Open and edit' })
    fireEvent.click(shortcut)
    const workspace = screen.getByRole('dialog', { name: 'Knowledge sources' })
    expect(workspace).toHaveClass('knowledge-workspace')
    expect(workspace).toHaveAttribute('open')
    expect(await screen.findByText('{}')).toBeInTheDocument()
    expect(within(workspace).getByRole('button', { name: 'README.md: Open and edit' })).toHaveAttribute('aria-current', 'true')
    fireEvent.click(within(workspace).getByRole('button', { name: 'Edit text' }))
    fireEvent.change(within(workspace).getByRole('textbox', { name: 'Edit text' }), { target: { value: 'Unsaved notes' } })
    fireEvent(workspace, new Event('cancel', { cancelable: true }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(shortcut).toHaveFocus()
    const openWorkspace = screen.getByRole('button', { name: 'Open knowledge workspace' })
    fireEvent.click(openWorkspace)
    expect(within(workspace).getByRole('textbox', { name: 'Edit text' })).toHaveValue('Unsaved notes')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    fireEvent.click(within(workspace).getByRole('button', { name: 'User Flow' }))
    fireEvent.click(within(workspace).getByRole('button', { name: 'checkout.json: Open and edit' }))
    expect(api.getResourceContent).toHaveBeenCalledTimes(1)
    fireEvent.click(within(workspace).getByRole('button', { name: 'checkout.json: Open and edit' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Edit text' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Edit text' }), { target: { value: '{"updated":true}' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(api.updateResourceContent).toHaveBeenCalledWith(1, 'user_flow', 'flow', '{"updated":true}'))
    confirm.mockRestore()
    fireEvent.click(within(workspace).getByRole('button', { name: 'Close knowledge workspace' }))
    expect(openWorkspace).toHaveFocus()
  })

  it('opens snapshot files in a read-only reader with syntax highlighting and a plain text fallback', async () => {
    const content = { 'script.py': 'def run():\n    return "<script>"', 'main.rs': 'fn main() {}', 'notes.unknown': '<script>alert(1)</script>' }
    const api = {
      getSource: vi.fn().mockResolvedValue(project),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 3 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'done', progress: 100, error: null }),
      getProjectIndexStatus: vi.fn().mockResolvedValue(indexStatus),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getSourceBrowserSnapshot: vi.fn().mockResolvedValue({ status: 'ready', snapshot_id: 8, branches: ['main', 'stable'] }),
      getSourceBrowserTree: vi.fn().mockResolvedValue({
        entries: Object.keys(content).map((path) => ({ name: path, path, kind: 'file' })),
        next_cursor: null,
      }),
      getSourceBrowserFile: vi.fn((_id, _snapshot, _branch, path: keyof typeof content) =>
        Promise.resolve({ status: 'ready', path, content: content[path] }),
      ),
    } as unknown as ApiClient
    renderProject(api)

    fireEvent.click(await screen.findByRole('button', { name: 'Source code' }))
    const workspace = screen.getByRole('dialog', { name: 'Knowledge sources' })
    fireEvent.click(await screen.findByRole('button', { name: 'script.py' }))
    const python = await screen.findByLabelText('script.py')
    await waitFor(() => expect(python.querySelector('.hljs-keyword')).toHaveTextContent('def'))
    expect(python).toHaveTextContent('return "<script>"')
    fireEvent.change(screen.getByRole('combobox', { name: 'Branch' }), { target: { value: 'stable' } })
    fireEvent.click(await screen.findByRole('button', { name: 'main.rs' }))
    const rust = await screen.findByLabelText('main.rs')
    await waitFor(() => expect(rust.querySelector('.hljs-keyword')).toHaveTextContent('fn'))
    expect(api.getSourceBrowserFile).toHaveBeenCalledWith(1, 8, 'stable', 'main.rs', expect.any(AbortSignal))
    fireEvent.click(screen.getByRole('button', { name: 'notes.unknown' }))
    const unknown = await screen.findByLabelText('notes.unknown')
    expect(unknown).toHaveTextContent(content['notes.unknown'])
    expect(unknown.querySelector('script, .hljs-keyword')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Edit text' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
    fireEvent.click(within(workspace).getByRole('button', { name: 'Close knowledge workspace' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open knowledge workspace' }))
    expect(screen.getByRole('combobox', { name: 'Branch' })).toHaveValue('stable')
    expect(within(workspace).getByLabelText('notes.unknown', { selector: 'pre' })).toHaveTextContent(content['notes.unknown'])
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
      getProjectIndexStatus: vi.fn().mockResolvedValue(indexStatus),
    } as unknown as ApiClient
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderProject(api)

    fireEvent.click(await screen.findByRole('button', { name: 'Open knowledge workspace' }))
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
      getProjectIndexStatus: vi.fn().mockResolvedValue(indexStatus),
    } as unknown as ApiClient
    renderProject(api)

    fireEvent.click(await screen.findByRole('button', { name: 'Open knowledge workspace' }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'Documentation source type' }), { target: { value: 'confluence' } })
    fireEvent.click(screen.getByTitle('Confluence'))
    expect(await screen.findByText('Confluence connection is not available yet. No files were added.')).toBeInTheDocument()
    expect(api.importLocalResource).not.toHaveBeenCalled()
  })

  it('hides generation actions unless experimental features are enabled', async () => {
    const api = {
      getSource: vi.fn().mockResolvedValue(project),
      getProjectStats: vi.fn().mockResolvedValue({ file_count: 12 }),
      getImportStatus: vi.fn().mockResolvedValue({ status: 'done', progress: 100, error: null }),
      listWorkspaceModels: vi.fn().mockResolvedValue([]),
      getProjectModelSelections: vi.fn().mockResolvedValue({ indexing: null, documentation_generation: null }),
      getProjectIndexStatus: vi.fn().mockResolvedValue(indexStatus),
    } as unknown as ApiClient
    const initial = renderProject(api)

    expect(await screen.findByText('sample')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Generate docs from code' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Generate User Flow from docs' })).not.toBeInTheDocument()
    expect(screen.queryByText('Generation model')).not.toBeInTheDocument()
    initial.unmount()

    render(
      <I18nProvider>
        <ProjectPage sourceId={1} api={api} experimental onBack={() => {}} />
      </I18nProvider>,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Open knowledge workspace' }))
    expect(await screen.findByRole('button', { name: 'Generate docs from code' })).toBeDisabled()
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'User Flow' }))
    expect(screen.getByRole('button', { name: 'Generate User Flow from docs' })).toBeDisabled()
    expect(screen.getByText('Generation model')).toBeInTheDocument()
  })
})
