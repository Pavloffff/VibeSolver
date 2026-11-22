import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import SolverGraphPage from '../pages/solver-graph-page'
import { I18nProvider } from '../shared/i18n'
import type { ApiClient } from '../shared/api/client'

it('saves a disabled triage step in the selected project profile', async () => {
  const profile = { id: 14, name: 'Support', enabled: { triage: true, resolve: true }, models: { ticket_resolution: 8, ticket_triage: null, ticket_resolution_cheap: null } }
  const graph = { profiles: [profile], default_profile_id: 14, nodes: ['triage', 'investigate', 'resolve', 'answer', 'escalate'].map(id => ({ id, optional: ['triage', 'resolve'].includes(id) })), edges: [{ source: 'triage', target: 'investigate' }, { source: 'investigate', target: 'resolve' }, { source: 'resolve', target: 'answer' }, { source: 'resolve', target: 'escalate' }] }
  const api = { getSolverGraph: vi.fn().mockResolvedValue(graph), listWorkspaceModels: vi.fn().mockResolvedValue([]), updateSolverProfile: vi.fn().mockResolvedValue(profile) }
  render(<I18nProvider><SolverGraphPage projectId={5} api={api as unknown as ApiClient} /></I18nProvider>)
  const toggle = await screen.findByRole('checkbox')
  fireEvent.click(toggle)
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  await waitFor(() => expect(api.updateSolverProfile).toHaveBeenCalledWith(5, 14, { name: 'Support', enabled: { triage: false, resolve: true }, models: profile.models }))
})
