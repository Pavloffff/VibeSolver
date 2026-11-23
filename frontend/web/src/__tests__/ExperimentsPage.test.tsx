import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import ExperimentsPage from '../pages/experiments-page/ExperimentsPage'
import type { ApiClient } from '../shared/api/client'
import { I18nProvider } from '../shared/i18n'

it('only loads an observation after the engineer selects its issue', async () => {
  const api = {
    listTickets: vi.fn().mockResolvedValue([{ id: 8, title: 'Settings layout' }, { id: 13, title: 'Open menu' }]),
    getUiObservation: vi.fn().mockResolvedValue({ observation: null }),
  }
  render(<I18nProvider><ExperimentsPage projectId={3} api={api as unknown as ApiClient} /></I18nProvider>)
  const picker = await screen.findByRole('combobox')
  expect(api.listTickets).toHaveBeenCalledWith(3)
  expect(api.getUiObservation).not.toHaveBeenCalled()
  fireEvent.change(picker, { target: { value: '13' } })
  await waitFor(() => expect(api.getUiObservation).toHaveBeenCalledWith(13))
  expect(await screen.findByRole('link')).toHaveAttribute('href', './ui-observer.html?lang=en')
})
