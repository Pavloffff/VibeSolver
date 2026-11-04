import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { ApiClient } from '../shared/api/client'
import SourcesPage from '../pages/sources-page'
import { I18nProvider } from '../shared/i18n'

const sources = [
  {
    id: 1,
    type: 'git',
    name: 'main repo',
    enabled: true,
    last_import: { status: 'done', finished_at: '2026-01-01T00:00:00Z' },
  },
  {
    id: 2,
    type: 'local_folder',
    name: 'docs',
    enabled: true,
    last_import: null,
  },
]

function makeApi(): ApiClient {
  return {
    listSources: vi.fn().mockResolvedValue(sources),
  } as unknown as ApiClient
}

beforeEach(() => {
  localStorage.setItem('vibesolver.lang', 'ru')
})

describe('SourcesPage', () => {
  it('renders source rows with names and import statuses', async () => {
    render(
      <I18nProvider>
        <SourcesPage api={makeApi()} />
      </I18nProvider>,
    )
    expect(await screen.findByText('main repo')).toBeInTheDocument()
    expect(screen.getByText('docs')).toBeInTheDocument()
    expect(screen.getByText('git')).toBeInTheDocument()
    expect(screen.getByText('local_folder')).toBeInTheDocument()
    expect(screen.getByText('Успешно')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'main repo' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Импорт' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Удалить' })).toHaveLength(2)
  })

  it('opens a project when its name is selected', async () => {
    const onProjectSelected = vi.fn()
    render(
      <I18nProvider>
        <SourcesPage api={makeApi()} onProjectSelected={onProjectSelected} />
      </I18nProvider>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'main repo' }))
    expect(onProjectSelected).toHaveBeenCalledWith(1)
  })

  it('shows English strings after switching to en', async () => {
    localStorage.setItem('vibesolver.lang', 'en')
    render(
      <I18nProvider>
        <SourcesPage api={makeApi()} />
      </I18nProvider>,
    )
    expect(await screen.findByText('main repo')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New project' })).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
    expect(screen.getByText('Import status')).toBeInTheDocument()
  })
})
