import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { SourceBrowser } from '../pages/project-page/ui/SourceBrowser'
import { t } from '../shared/i18n'

it('keeps the selected snapshot and renders imported markup as text', async () => {
  const api = {
    getSourceBrowserSnapshot: vi.fn().mockResolvedValue({ status: 'ready', snapshot_id: 12, branches: ['main'] }),
    getSourceBrowserTree: vi.fn().mockResolvedValue({
      entries: [{ kind: 'file', name: 'index.html', path: 'index.html', size_bytes: 15 }],
      next_cursor: null,
    }),
    getSourceBrowserFile: vi.fn().mockResolvedValue({
      status: 'ready', path: 'index.html', content: '<b>not HTML</b>',
    }),
  }
  render(<SourceBrowser sourceId={1} api={api} t={(key) => t('en', key)} />)
  fireEvent.click(screen.getByRole('button', { name: 'Browse source code' }))
  fireEvent.click(await screen.findByRole('button', { name: 'index.html' }))
  expect(await screen.findByText('<b>not HTML</b>')).toBeInTheDocument()
  expect(api.getSourceBrowserFile).toHaveBeenCalledWith(1, 12, 'main', 'index.html', expect.any(AbortSignal))
})

it('keeps the folder cursor with its branch and clears the preview on branch change', async () => {
  const api = {
    getSourceBrowserSnapshot: vi.fn().mockResolvedValue({
      status: 'ready', snapshot_id: 12, branches: ['main', 'feature/one'],
    }),
    getSourceBrowserTree: vi.fn()
      .mockResolvedValueOnce({
        entries: [{ kind: 'directory', name: 'src', path: 'src', size_bytes: null }],
        next_cursor: null,
      })
      .mockResolvedValueOnce({ entries: [], next_cursor: 'next' })
      .mockResolvedValueOnce({
        entries: [{ kind: 'file', name: 'asset.dat', path: 'src/asset.dat', size_bytes: 2 }],
        next_cursor: null,
      })
      .mockResolvedValueOnce({ entries: [], next_cursor: null }),
    getSourceBrowserFile: vi.fn().mockResolvedValue({
      status: 'binary', path: 'src/asset.dat', content: null,
    }),
  }
  render(<SourceBrowser sourceId={1} api={api} t={(key) => t('en', key)} />)
  fireEvent.click(screen.getByRole('button', { name: 'Browse source code' }))
  fireEvent.click(await screen.findByRole('button', { name: 'src' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Load more' }))
  fireEvent.click(await screen.findByRole('button', { name: 'asset.dat' }))
  expect(await screen.findByText('This is a binary file. A text preview is unavailable.')).toBeInTheDocument()
  expect(api.getSourceBrowserTree).toHaveBeenNthCalledWith(3, 1, 12, 'main', 'src', 'next')

  fireEvent.change(screen.getByRole('combobox', { name: 'Branch' }), { target: { value: 'feature/one' } })
  expect(await screen.findByText('This folder is empty.')).toBeInTheDocument()
  expect(api.getSourceBrowserTree).toHaveBeenLastCalledWith(1, 12, 'feature/one', '', null, expect.any(AbortSignal))
  expect(screen.queryByText('src/asset.dat')).not.toBeInTheDocument()
})
