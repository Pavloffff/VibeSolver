import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { ApiClient } from '../api/client'
import SourceForm from '../components/SourceForm'
import { I18nProvider } from '../i18n'

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
    createSource: vi.fn().mockResolvedValue({}),
  } as unknown as ApiClient
}

function renderForm() {
  render(
    <I18nProvider>
      <SourceForm api={makeApi()} onCreated={() => {}} onClose={() => {}} />
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
})
