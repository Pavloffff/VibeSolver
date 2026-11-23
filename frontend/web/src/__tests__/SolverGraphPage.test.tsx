import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import SolverGraphPage from '../pages/solver-graph-page'
import { I18nProvider } from '../shared/i18n'
import type { ApiClient } from '../shared/api/client'
import type { DiagnosticTools, SolverProfile, SolverProfileInput } from '../shared/api/types'

const supportProfile: SolverProfile = {
  id: 14,
  name: 'Support',
  enabled: { triage: true, resolve: true },
  models: { ticket_resolution: 8, ticket_triage: null, ticket_resolution_cheap: null },
}
const installedModel = { id: 8, provider_name: 'Local', display_name: 'Support model', status: 'installed' }
const supportGraph = { default_profile_id: null, nodes: [{ id: 'triage', optional: true }, { id: 'resolve', optional: true }], edges: [] }

function renderGraph(api: object) {
  return render(<I18nProvider><SolverGraphPage projectId={5} api={api as ApiClient} /></I18nProvider>)
}

it('requires the engineer to create the first profile and can remove the last one', async () => {
  const graph = { profiles: [], nodes: [{ id: 'resolve', optional: true }], edges: [], default_profile_id: null }
  const api = {
    getSolverGraph: vi.fn().mockResolvedValue(graph),
    listWorkspaceModels: vi.fn().mockResolvedValue([{ id: 8, provider_name: 'Local', display_name: 'Support model', status: 'installed' }]),
    createSolverProfile: vi.fn().mockImplementation((_source, input) => Promise.resolve({ ...input, id: 24 })),
    deleteSolverProfile: vi.fn().mockResolvedValue(undefined),
  }
  render(<I18nProvider><SolverGraphPage projectId={5} api={api as unknown as ApiClient} /></I18nProvider>)
  fireEvent.click(await screen.findByRole('button', { name: 'Create profile' }))
  fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'Lab support' } })
  fireEvent.blur(screen.getByLabelText('Profile name'))
  expect(api.createSolverProfile).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Primary answer model'), { target: { value: '8' } })
  await waitFor(() => expect(api.createSolverProfile).toHaveBeenCalledTimes(1))
  fireEvent.click(await screen.findByRole('button', { name: 'Delete profile' }))
  fireEvent.click(screen.getAllByRole('button', { name: 'Delete profile' }).at(-1)!)
  expect(await screen.findByRole('button', { name: 'Create profile' })).toBeVisible()
  expect(api.deleteSolverProfile).toHaveBeenCalledWith(5, 24)
})

it('serializes fast profile changes and finishes the latest change after navigation', async () => {
  let latest = supportProfile
  let finishFirst: () => void = () => {}
  const firstWrite = new Promise<void>(resolve => { finishFirst = resolve })
  const api = {
    getSolverGraph: vi.fn().mockImplementation(() => Promise.resolve({ ...supportGraph, profiles: [latest] })),
    listWorkspaceModels: vi.fn().mockResolvedValue([installedModel]),
    updateSolverProfile: vi.fn().mockImplementationOnce(async (_source, id: number, input: SolverProfileInput) => {
      await firstWrite
      latest = { ...input, id }
      return latest
    }).mockImplementation(async (_source, id: number, input: SolverProfileInput) => {
      latest = { ...input, id }
      return latest
    }),
  }
  const page = renderGraph(api)
  const toggle = await screen.findByRole('checkbox', { name: 'Run this agent' })
  fireEvent.click(toggle)
  fireEvent.click(toggle)
  expect(toggle).toBeChecked()
  expect(api.updateSolverProfile).toHaveBeenCalledTimes(1)
  page.unmount()
  renderGraph(api)
  expect(api.getSolverGraph).toHaveBeenCalledTimes(1)
  await act(async () => finishFirst())
  const reloadedToggle = await screen.findByRole('checkbox', { name: 'Run this agent' })
  expect(reloadedToggle).toBeChecked()
  expect(api.updateSolverProfile).toHaveBeenCalledTimes(2)
  expect(api.updateSolverProfile.mock.calls.map(([, , input]) => input.enabled.triage)).toEqual([false, true])
})

it('applies a valid rename on blur and creates one explicitly requested custom clone', async () => {
  let finishCreate: (result: SolverProfile) => void = () => {}
  const creating = new Promise<SolverProfile>(resolve => { finishCreate = resolve })
  const api = {
    getSolverGraph: vi.fn().mockResolvedValue({ ...supportGraph, profiles: [supportProfile] }),
    listWorkspaceModels: vi.fn().mockResolvedValue([installedModel]),
    updateSolverProfile: vi.fn().mockImplementation((_source, id: number, input: SolverProfileInput) => Promise.resolve({ ...input, id })),
    createSolverProfile: vi.fn().mockReturnValue(creating),
  }
  renderGraph(api)
  fireEvent.click(await screen.findByRole('button', { name: 'Edit profile name' }))
  const rename = screen.getByRole('textbox', { name: 'Profile name' })
  fireEvent.change(rename, { target: { value: '   ' } })
  fireEvent.blur(rename)
  expect(api.updateSolverProfile).not.toHaveBeenCalled()
  fireEvent.change(rename, { target: { value: 'New support' } })
  fireEvent.blur(rename)
  expect(api.updateSolverProfile).toHaveBeenCalledWith(5, 14, expect.objectContaining({ name: 'New support' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'New profile' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'New profile' }))
  const cloneName = screen.getByRole('textbox', { name: 'Profile name' })
  expect(cloneName).toHaveValue('Copy of New support')
  expect(api.createSolverProfile).not.toHaveBeenCalled()
  fireEvent.change(cloneName, { target: { value: 'Custom clone' } })
  fireEvent.blur(cloneName)
  fireEvent.blur(cloneName)
  expect(api.createSolverProfile).toHaveBeenCalledExactlyOnceWith(5, expect.objectContaining({ name: 'Custom clone' }))
  await act(async () => finishCreate({ ...supportProfile, id: 15, name: 'Custom clone' }))
  expect(screen.getByRole('combobox', { name: 'Run profile' })).toHaveValue('15')
})

it('keeps failed diagnostic changes visible and retries the same values after navigation', async () => {
  const tools: DiagnosticTools = { allow_web_search: false, ui_probe: null, web_provider: 'search-a', available_ui_probes: [], available_web_providers: ['search-a'] }
  const api = {
    getSolverGraph: vi.fn().mockResolvedValue({ ...supportGraph, profiles: [supportProfile] }),
    listWorkspaceModels: vi.fn().mockResolvedValue([]),
    getDiagnosticTools: vi.fn().mockResolvedValue(tools),
    setDiagnosticTools: vi.fn().mockRejectedValueOnce(new Error('Update conflict')).mockResolvedValue({ ...tools, allow_web_search: true }),
  }
  const page = renderGraph(api)
  fireEvent.click(await screen.findByRole('checkbox', { name: 'Allow web search' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Update conflict')
  page.unmount()
  renderGraph(api)
  expect(await screen.findByRole('alert')).toHaveTextContent('Changes could not be applied.')
  expect(screen.getByRole('checkbox', { name: 'Allow web search' })).toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('Changes applied')).toBeInTheDocument()
  expect(api.setDiagnosticTools.mock.calls).toEqual([
    [5, { ui_probe: null, web_provider: 'search-a', allow_web_search: true }],
    [5, { ui_probe: null, web_provider: 'search-a', allow_web_search: true }],
  ])
})

it('requires a configured provider for consent, preserves consent on switching and revokes it on clearing', async () => {
  const tools: DiagnosticTools = { allow_web_search: false, ui_probe: null, web_provider: null, available_ui_probes: [], available_web_providers: ['search-a', 'search-b'] }
  const api = {
    getSolverGraph: vi.fn().mockResolvedValue({ ...supportGraph, profiles: [supportProfile] }),
    listWorkspaceModels: vi.fn().mockResolvedValue([]),
    getDiagnosticTools: vi.fn().mockResolvedValue(tools),
    setDiagnosticTools: vi.fn().mockImplementation((_project, input) => Promise.resolve({ ...tools, ...input })),
  }
  renderGraph(api)
  const consent = await screen.findByRole('checkbox', { name: 'Allow web search' })
  const provider = screen.getByLabelText('Web search provider')
  expect(consent).toBeDisabled()
  expect(consent).toHaveAccessibleDescription('Select a search provider to enable web search.')
  expect(api.setDiagnosticTools).not.toHaveBeenCalled()
  fireEvent.change(provider, { target: { value: 'search-a' } })
  expect(consent).toBeEnabled()
  fireEvent.click(consent)
  await waitFor(() => expect(api.setDiagnosticTools).toHaveBeenLastCalledWith(5, { ui_probe: null, web_provider: 'search-a', allow_web_search: true }))
  fireEvent.change(provider, { target: { value: 'search-b' } })
  await waitFor(() => expect(api.setDiagnosticTools).toHaveBeenLastCalledWith(5, { ui_probe: null, web_provider: 'search-b', allow_web_search: true }))
  fireEvent.change(provider, { target: { value: '' } })
  expect(consent).toBeDisabled()
  expect(consent).not.toBeChecked()
  await waitFor(() => expect(api.setDiagnosticTools).toHaveBeenLastCalledWith(5, { ui_probe: null, web_provider: null, allow_web_search: false }))
})

it('shows a stale provider and lets the engineer revoke previously granted consent', async () => {
  const tools: DiagnosticTools = { allow_web_search: true, ui_probe: null, web_provider: 'removed', available_ui_probes: [], available_web_providers: ['search-a'] }
  const api = {
    getSolverGraph: vi.fn().mockResolvedValue({ ...supportGraph, profiles: [supportProfile] }),
    listWorkspaceModels: vi.fn().mockResolvedValue([]),
    getDiagnosticTools: vi.fn().mockResolvedValue(tools),
    setDiagnosticTools: vi.fn().mockImplementation((_project, input) => Promise.resolve({ ...tools, ...input })),
  }
  renderGraph(api)
  const consent = await screen.findByRole('checkbox', { name: 'Allow web search' })
  expect(screen.getByRole('option', { name: 'Unavailable provider: removed' })).toHaveProperty('selected', true)
  expect(consent).toBeChecked()
  expect(consent).toBeEnabled()
  fireEvent.click(consent)
  await waitFor(() => expect(api.setDiagnosticTools).toHaveBeenCalledExactlyOnceWith(5, { ui_probe: null, web_provider: null, allow_web_search: false }))
  expect(consent).toBeDisabled()
})

it('saves a disabled triage step in the selected project profile', async () => {
  const profile = { id: 14, name: 'Support', enabled: { triage: true, resolve: true }, models: { ticket_resolution: 8, ticket_triage: null, ticket_resolution_cheap: null } }
  const graph = { profiles: [profile], default_profile_id: 14, nodes: ['triage', 'investigate', 'resolve', 'answer', 'escalate'].map(id => ({ id, optional: ['triage', 'resolve'].includes(id) })), edges: [{ source: 'triage', target: 'investigate' }, { source: 'investigate', target: 'resolve' }, { source: 'resolve', target: 'answer' }, { source: 'resolve', target: 'escalate' }] }
  const api = { getSolverGraph: vi.fn().mockResolvedValue(graph), listWorkspaceModels: vi.fn().mockResolvedValue([]), updateSolverProfile: vi.fn().mockResolvedValue(profile) }
  render(<I18nProvider><SolverGraphPage projectId={5} api={api as unknown as ApiClient} /></I18nProvider>)
  const toggle = await screen.findByRole('checkbox')
  fireEvent.click(toggle)
  await waitFor(() => expect(api.updateSolverProfile).toHaveBeenCalledWith(5, 14, { name: 'Support', enabled: { triage: false, resolve: true }, models: profile.models }))
})

it('edits specialist switches and project diagnostic tools', async () => {
  const profile = { id: 14, name: 'Support', enabled: { triage: true, resolve: true }, models: { ticket_resolution: 8, ticket_triage: null, ticket_resolution_cheap: null } }
  const graph = { profiles: [profile], default_profile_id: 14, nodes: [{ id: 'triage', optional: true }, { id: 'code', optional: true }], edges: [{ source: 'triage', target: 'code' }] }
  const tools = { ui_probe: null, web_provider: null, available_ui_probes: ['browser-a'], available_web_providers: ['search-a'] }
  const api = { getSolverGraph: vi.fn().mockResolvedValue(graph), listWorkspaceModels: vi.fn().mockResolvedValue([]), getDiagnosticTools: vi.fn().mockResolvedValue(tools), setDiagnosticTools: vi.fn().mockResolvedValue({ ...tools, web_provider: 'search-a' }), updateSolverProfile: vi.fn().mockImplementation((_id, _pid, input) => Promise.resolve({ ...profile, ...input })) }
  render(<I18nProvider><SolverGraphPage projectId={5} api={api as unknown as ApiClient} /></I18nProvider>)
  fireEvent.click(await screen.findByRole('button', { name: /Inspect code/ }))
  fireEvent.click(screen.getByRole('checkbox', { name: /Run this agent/ }))
  await waitFor(() => expect(api.updateSolverProfile).toHaveBeenCalledWith(5, 14, expect.objectContaining({ enabled: expect.objectContaining({ code: true }) })))
  fireEvent.change(screen.getByLabelText('Web search provider'), { target: { value: 'search-a' } })
  fireEvent.click(screen.getByRole('checkbox', { name: 'Allow web search' }))
  await waitFor(() => expect(api.setDiagnosticTools).toHaveBeenCalledWith(5, { ui_probe: null, web_provider: 'search-a', allow_web_search: true }))
  expect(screen.queryByRole('button', { name: /Save changes|Save diagnostic tools/ })).not.toBeInTheDocument()
})
