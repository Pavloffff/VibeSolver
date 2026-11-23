import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import ModelsPage from '../pages/models-page'
import type { OllamaPullProgress } from '../shared/api/types'
import { I18nProvider } from '../shared/i18n'

const modelApi = vi.hoisted(() => ({
  listModelProviderTypes: vi.fn(),
  listModelProviders: vi.fn(),
  listWorkspaceModels: vi.fn(),
  pullOllamaModel: vi.fn(),
  updateModelProvider: vi.fn(),
  testSavedModelProvider: vi.fn(),
  createModelProvider: vi.fn(),
}))

vi.mock('../shared/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../shared/api/client')>()),
  getApiClient: () => modelApi,
}))

beforeEach(() => {
  localStorage.setItem('vibesolver.lang', 'zh')
  vi.clearAllMocks()
  modelApi.listModelProviderTypes.mockResolvedValue([
    {
      provider_type: 'kimi', display_name: 'Kimi (Moonshot)', supports_model_pull: false,
    },
    {
      provider_type: 'ollama', display_name: 'Ollama', supports_model_pull: true,
    },
  ])
  modelApi.listModelProviders.mockResolvedValue([
    { id: 7, provider_type: 'ollama', name: 'Engineering lab', base_url: 'http://localhost' },
  ])
  modelApi.listWorkspaceModels.mockResolvedValue([
    {
      id: 8, provider_connection_id: 7, provider_name: 'Engineering lab', provider_model_id: 'custom:1',
      display_name: 'Custom model', status: 'installed', capabilities: ['chat'], metadata: {},
    },
  ])
})

function renderModels() {
  render(<I18nProvider><ModelsPage /></I18nProvider>)
}

it('localizes catalog metadata while preserving provider and model names', async () => {
  renderModels()
  expect(await screen.findByRole('heading', { name: 'Engineering lab' })).toBeInTheDocument()
  expect(screen.getByText('Custom model')).toBeInTheDocument()
  expect(screen.getByText('文本生成')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /添加提供商/ }))
  const form = screen.getByRole('dialog')
  expect(within(form).getByRole('option', { name: 'Kimi（月之暗面）' })).toHaveValue('kimi')
})

it('renders model download progress in the selected language', async () => {
  modelApi.pullOllamaModel.mockImplementation(
    async (_id: number, _model: string, progress: (event: OllamaPullProgress) => void) => {
      progress({ status: 'verifying sha256 digest', progress: 99 })
    },
  )
  renderModels()
  fireEvent.click(await screen.findByRole('button', { name: '下载模型' }))
  const form = screen.getByRole('dialog')
  fireEvent.change(within(form).getByLabelText('模型标签'), { target: { value: 'custom:2' } })
  fireEvent.click(within(form).getByRole('button', { name: '下载模型' }))
  expect(await within(form).findByText('正在验证模型文件…')).toBeInTheDocument()
  expect(within(form).queryByText('verifying sha256 digest')).not.toBeInTheDocument()
})


it('applies connection edits on Enter and blur, preserving a pending draft and an empty key', async () => {
  localStorage.setItem('vibesolver.lang', 'en')
  const saved = { id: 7, provider_type: 'ollama', name: 'Updated lab', base_url: 'http://localhost', has_api_key: true }
  let finishRename: (provider: typeof saved) => void = () => undefined
  modelApi.updateModelProvider
    .mockImplementationOnce(() => new Promise<typeof saved>(resolve => { finishRename = resolve }))
    .mockResolvedValueOnce({ ...saved, base_url: 'http://127.0.0.1:11434' })
  renderModels()
  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
  const form = screen.getByRole('dialog')
  const name = within(form).getByLabelText('Connection name')
  const address = within(form).getByLabelText('API address')
  expect(within(form).queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()

  name.focus()
  fireEvent.change(name, { target: { value: 'Updated lab' } })
  fireEvent.keyDown(name, { key: 'Enter' })
  await waitFor(() => expect(modelApi.updateModelProvider).toHaveBeenCalledWith(7, { name: 'Updated lab' }))
  fireEvent.change(address, { target: { value: 'http://127.0.0.1:11434' } })
  fireEvent.blur(address)
  fireEvent.blur(within(form).getByLabelText('API key'))
  finishRename(saved)

  await waitFor(() => expect(modelApi.updateModelProvider).toHaveBeenNthCalledWith(2, 7, {
    name: 'Updated lab', base_url: 'http://127.0.0.1:11434',
  }))
  expect(address).toHaveValue('http://127.0.0.1:11434')
  expect(modelApi.updateModelProvider).toHaveBeenCalledTimes(2)
  expect(modelApi.listModelProviders).toHaveBeenCalledTimes(1)
  expect(modelApi.testSavedModelProvider).not.toHaveBeenCalled()
  expect(modelApi.createModelProvider).not.toHaveBeenCalled()
})

it('displays errors for invalid and rejected edits while keeping the editor open', async () => {
  localStorage.setItem('vibesolver.lang', 'en')
  modelApi.updateModelProvider.mockRejectedValueOnce(new Error('Connection update was rejected'))
  renderModels()
  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
  const form = screen.getByRole('dialog')

  const address = within(form).getByLabelText('API address')
  fireEvent.change(address, { target: { value: 'not an address' } })
  fireEvent.blur(address)
  expect(within(form).getByRole('alert')).toHaveTextContent('Enter an HTTP(S) address')
  expect(modelApi.updateModelProvider).not.toHaveBeenCalled()

  fireEvent.change(address, { target: { value: 'http://127.0.0.1:8888' } })
  fireEvent.blur(address)
  expect(await within(form).findByText('Connection update was rejected')).toBeInTheDocument()
  fireEvent.click(within(form).getByRole('button', { name: 'Done' }))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})


it('creates a provider only after the engineer completes the form and adds the connection', async () => {
  localStorage.setItem('vibesolver.lang', 'en')
  modelApi.listModelProviderTypes.mockResolvedValue([{
    provider_type: 'kimi',
    display_name: 'Kimi (Moonshot)',
    default_url: 'https://example.test/v1',
    requires_api_key: true,
    fixed_url: true,
    sync_all_models: true,
  }])
  modelApi.createModelProvider.mockResolvedValue({
    id: 9, provider_type: 'kimi', name: 'Secondary lab', base_url: 'https://example.test/v1', has_api_key: true,
  })
  renderModels()
  fireEvent.click(await screen.findByRole('button', { name: /Add provider/ }))
  const form = screen.getByRole('dialog')
  const name = within(form).getByLabelText('Connection name')
  fireEvent.change(name, { target: { value: 'Secondary lab' } })
  fireEvent.blur(name)
  fireEvent.click(within(form).getByRole('button', { name: 'Add connection' }))
  expect(modelApi.createModelProvider).not.toHaveBeenCalled()

  fireEvent.change(within(form).getByLabelText(/API key/), { target: { value: 'test-key' } })
  fireEvent.click(within(form).getByRole('button', { name: 'Add connection' }))
  await waitFor(() => expect(modelApi.createModelProvider).toHaveBeenCalledOnce())
  expect(modelApi.createModelProvider).toHaveBeenCalledWith({
    provider_type: 'kimi', name: 'Secondary lab', base_url: 'https://example.test/v1', api_key: 'test-key',
  })
})
