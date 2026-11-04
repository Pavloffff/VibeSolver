import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ApiClient } from '../shared/api/client'
import SourceForm from '../features/add-source'
import { I18nProvider } from '../shared/i18n'

const connectors = [
  {
    type: 'git',
    ready: true,
    config_schema: {
      fields: [{ name: 'url', label: 'URL', kind: 'text' as const, required: true }],
    },
  },
  {
    type: 'svn',
    ready: false,
    config_schema: { fields: [] },
  },
]

function makeApi(): ApiClient {
  return {
    listConnectors: vi.fn().mockResolvedValue(connectors),
    createSource: vi.fn().mockResolvedValue({ id: 8 }),
    startImport: vi.fn().mockResolvedValue({ task_id: 'task-8' }),
  } as unknown as ApiClient
}

function renderForm() {
  render(
    <I18nProvider>
      <SourceForm api={makeApi()} onCreated={() => {}} onClose={() => {}} />
    </I18nProvider>,
  )
}

function renderArchiveForm(api: ApiClient) {
  render(
    <I18nProvider>
      <SourceForm api={api} onCreated={() => {}} onClose={() => {}} />
    </I18nProvider>,
  )
}

beforeEach(() => {
  localStorage.setItem('vibesolver.lang', 'ru')
})

describe('SourceForm', () => {
  it('marks not-ready connectors as disabled', async () => {
    renderForm()
    const gitOption = await screen.findByRole('option', { name: 'git' })
    const svnOption = screen.getByRole('option', { name: /svn/ })
    expect(gitOption).toBeEnabled()
    expect(svnOption).toBeDisabled()
  })

  it('renders config fields from schema of selected connector', async () => {
    renderForm()
    const select = await screen.findByRole('combobox')
    fireEvent.change(select, { target: { value: 'git' } })
    expect(screen.getByLabelText('URL *')).toBeInTheDocument()
  })

  it('shows required-field error in the current language', async () => {
    renderForm()
    const select = await screen.findByRole('combobox')
    fireEvent.change(select, { target: { value: 'git' } })
    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'repo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Создать' }))
    expect(await screen.findByText('Заполните поле «URL»')).toBeInTheDocument()
  })

  it('uploads an archive and creates the source with its upload key', async () => {
    const api = {
      listConnectors: vi.fn().mockResolvedValue([
        {
          type: 'archive',
          ready: true,
          config_schema: {
            fields: [{ name: 'upload_key', label: 'Archive file', kind: 'file' as const, required: true }],
          },
        },
      ]),
      uploadArchive: vi.fn().mockResolvedValue({ upload_key: 'uploads/archive-1' }),
      createSource: vi.fn().mockResolvedValue({ id: 4 }),
      startImport: vi.fn().mockResolvedValue({ task_id: 'task-4' }),
    } as unknown as ApiClient
    renderArchiveForm(api)
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'archive' } })
    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Проект' } })
    const file = new File(['source'], 'project.zip', { type: 'application/zip' })
    fireEvent.change(screen.getByLabelText(/Архив проекта/), { target: { files: [file] } })
    await waitFor(() => expect(api.uploadArchive).toHaveBeenCalledWith(file))
    fireEvent.click(screen.getByRole('button', { name: 'Создать' }))
    await waitFor(() =>
      expect(api.createSource).toHaveBeenCalledWith('archive', 'Проект', {
        upload_key: 'uploads/archive-1',
      }),
    )
    expect(api.startImport).toHaveBeenCalledWith(4)
  })

  it('continues to the project page if the automatic import cannot be queued', async () => {
    const onCreated = vi.fn()
    const api = {
      listConnectors: vi.fn().mockResolvedValue(connectors),
      createSource: vi.fn().mockResolvedValue({ id: 9 }),
      startImport: vi.fn().mockRejectedValue(new Error('queue unavailable')),
    } as unknown as ApiClient
    render(
      <I18nProvider>
        <SourceForm api={api} onCreated={onCreated} onClose={() => {}} />
      </I18nProvider>,
    )
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'git' } })
    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'repo' } })
    fireEvent.change(screen.getByLabelText('URL *'), { target: { value: 'https://github.com/acme/repo.git' } })
    fireEvent.click(screen.getByRole('button', { name: 'Создать' }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith({ id: 9 }, 'queue unavailable'))
  })
})
