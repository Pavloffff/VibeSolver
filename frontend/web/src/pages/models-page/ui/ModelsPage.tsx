import { useCallback, useEffect, useRef, useState } from 'react'
import { getApiClient, getErrorMessage } from '../../../shared/api/client'
import type { AvailableModel, ModelProvider, ModelProviderType, OllamaPullProgress, WorkspaceModel } from '../../../shared/api/types'
import { useT } from '../../../shared/i18n'
import type { TranslationKey } from '../../../shared/i18n'
import { modelCapabilityLabel, modelPullStatusLabel, modelStatusLabel, providerCatalogLabel } from '../../../shared/i18n/catalogLabels'

const PROVIDER_HINT_KEYS: Record<string, TranslationKey> = {
  freetoken: 'models.freetokenHint',
  zai: 'models.zaiHint',
  kimi: 'models.kimiHint',
  anthropic: 'models.anthropicHint',
  openai: 'models.openaiHint',
}

interface ProviderFormState {
  providerType: string
  name: string
  baseUrl: string
  apiKey: string
}

type ProviderField = 'name' | 'baseUrl' | 'apiKey'

interface ProviderEdit {
  saved: ModelProvider
  pending: Promise<void>
  scheduled: Map<ProviderField, { value: string }>
  errors: Map<ProviderField, string>
}

export default function ModelsPage() {
  const { lang, t } = useT()
  const api = getApiClient()
  const [providerTypes, setProviderTypes] = useState<ModelProviderType[]>([])
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [models, setModels] = useState<WorkspaceModel[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [form, setForm] = useState<ProviderFormState | null>(null)
  const [editingProvider, setEditingProvider] = useState<ModelProvider | null>(null)
  const [browseProvider, setBrowseProvider] = useState<ModelProvider | null>(null)
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([])
  const [search, setSearch] = useState('')
  const [pullProvider, setPullProvider] = useState<ModelProvider | null>(null)
  const [pullTag, setPullTag] = useState('')
  const [pullProgress, setPullProgress] = useState<OllamaPullProgress | null>(null)
  const abortController = useRef<AbortController | null>(null)
  const activeEdit = useRef<ProviderEdit | null>(null)

  const refresh = useCallback(async () => {
    const [catalog, connections, listedModels] = await Promise.all([
      api.listModelProviderTypes(),
      api.listModelProviders(),
      api.listWorkspaceModels(),
    ])
    setProviderTypes(catalog)
    setProviders(connections)
    setModels(listedModels)
  }, [api])

  useEffect(() => {
    let cancelled = false
    void refresh().catch((loadError: unknown) => {
      if (!cancelled) setError(getErrorMessage(loadError))
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [refresh])

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key)
    setError(null)
    setNotice(null)
    try {
      await action()
    } catch (actionError) {
      setError(getErrorMessage(actionError))
    } finally {
      setBusy(null)
    }
  }

  const openCreate = () => {
    const type = providerTypes[0]
    if (type === undefined) return
    activeEdit.current = null
    setError(null)
    setEditingProvider(null)
    setForm({ providerType: type.provider_type, name: type.display_name, baseUrl: type.default_url, apiKey: '' })
  }

  const openEdit = (provider: ModelProvider) => {
    activeEdit.current = { saved: provider, pending: Promise.resolve(), scheduled: new Map(), errors: new Map() }
    setError(null)
    setEditingProvider(provider)
    setForm({ providerType: provider.provider_type, name: provider.name, baseUrl: provider.base_url, apiKey: '' })
  }

  const closeProviderForm = () => {
    activeEdit.current = null
    setForm(null)
    setEditingProvider(null)
  }

  const finishProviderEdit = async (discardInvalid = false) => {
    const edit = activeEdit.current
    if (edit === null) {
      closeProviderForm()
      return
    }
    await edit.pending
    if (activeEdit.current === edit && (discardInvalid || edit.errors.size === 0)) closeProviderForm()
  }

  const createProvider = async (event: React.FormEvent) => {
    event.preventDefault()
    if (form === null || editingProvider !== null) return
    if (!form.name.trim()) {
      setError(t('catalog.providerNameRequired'))
      return
    }
    await run('provider-save', async () => {
      const createdProvider = await api.createModelProvider({
        provider_type: form.providerType,
        name: form.name.trim(),
        base_url: form.baseUrl.trim(),
        ...(form.apiKey.trim() ? { api_key: form.apiKey.trim() } : {}),
      })
      closeProviderForm()
      setProviders(previous => [...previous, createdProvider])
      setNotice(t('models.providerAdded'))
      await refresh()
      const definition = providerTypes.find((item) => item.provider_type === createdProvider.provider_type)
      if (definition && !definition.sync_all_models) {
        setAvailableModels(await api.listAvailableModels(createdProvider.id))
        setSearch('')
        setBrowseProvider(createdProvider)
      }
    })
  }

  const applyProviderField = (field: ProviderField, raw: string): void => {
    const edit = activeEdit.current
    if (edit === null) return
    const value = raw.trim()
    if (field === 'apiKey' && !value) {
      edit.errors.delete(field)
      setError([...edit.errors.values()][0] ?? null)
      return
    }
    const problem = field === 'name' && !value
      ? t('catalog.providerNameRequired')
      : field === 'baseUrl' && !validProviderAddress(value) ? t('catalog.providerInvalidAddress') : null
    if (problem !== null) {
      edit.errors.set(field, problem)
      setError(problem)
      return
    }
    if (edit.scheduled.get(field)?.value === value) return
    const change = { value }
    edit.scheduled.set(field, change)
    edit.pending = edit.pending.then(async () => {
      try {
        const { saved } = edit
        if ((field === 'name' && value === saved.name) || (field === 'baseUrl' && value === saved.base_url)) {
          edit.errors.delete(field)
          return
        }
        const updated = await api.updateModelProvider(saved.id, {
          name: field === 'name' ? value : saved.name,
          ...(field === 'baseUrl' ? { base_url: value } : {}),
          ...(field === 'apiKey' ? { api_key: value } : {}),
        })
        edit.saved = updated
        edit.errors.delete(field)
        setProviders(previous => previous.map(provider => provider.id === updated.id ? updated : provider))
        setModels(previous => previous.map(model => model.provider_connection_id === updated.id
          ? { ...model, provider_name: updated.name }
          : model))
        if (activeEdit.current === edit) {
          setForm(current => current && current[field].trim() === value ? {
            ...current,
            [field]: field === 'name' ? updated.name : field === 'baseUrl' ? updated.base_url : '',
          } : current)
        }
        setNotice(t('models.providerUpdated'))
      } catch (updateError) {
        edit.errors.set(field, getErrorMessage(updateError))
      } finally {
        if (edit.scheduled.get(field) === change) edit.scheduled.delete(field)
        if (activeEdit.current === edit || activeEdit.current === null) {
          setError([...edit.errors.values()][0] ?? null)
        }
      }
    })
  }

  const blurOnEnter = (event: React.KeyboardEvent<HTMLInputElement>): void => {
    if (editingProvider !== null && event.key === 'Enter') {
      event.preventDefault()
      event.currentTarget.blur()
    }
  }

  const testProviderForm = async () => {
    if (form === null) return
    const edit = activeEdit.current
    if (edit !== null) {
      await edit.pending
      if (activeEdit.current !== edit || edit.errors.size > 0) return
    }
    await run('provider-test', async () => {
      const result = edit !== null
        ? await api.testSavedModelProvider(edit.saved.id)
        : await api.testModelProvider({
          provider_type: form.providerType,
          name: form.name,
          base_url: form.baseUrl,
          ...(form.apiKey ? { api_key: form.apiKey } : {}),
        })
      setNotice(t('models.connectionTestOk', { count: String(result.available_models) }))
    })
  }

  const testProvider = (provider: ModelProvider) => {
    void run(`provider-test-${provider.id}`, async () => {
      const result = await api.testSavedModelProvider(provider.id)
      setNotice(t('models.connectionTestOk', { count: String(result.available_models) }))
    })
  }

  const deleteProvider = (provider: ModelProvider) => {
    if (!window.confirm(t('models.confirmDeleteProvider'))) return
    void run(`provider-delete-${provider.id}`, async () => {
      await api.deleteModelProvider(provider.id)
      await refresh()
      setNotice(t('models.providerRemoved'))
    })
  }

  const syncProvider = (provider: ModelProvider) => {
    void run(`provider-sync-${provider.id}`, async () => {
      await api.syncProviderModels(provider.id)
      await refresh()
      setNotice(t('models.synced'))
    })
  }

  const browseModels = async (provider: ModelProvider) => {
    setBusy(`provider-browse-${provider.id}`)
    setError(null)
    try {
      setAvailableModels(await api.listAvailableModels(provider.id))
      setSearch('')
      setBrowseProvider(provider)
    } catch (browseError) {
      setError(getErrorMessage(browseError))
    } finally {
      setBusy(null)
    }
  }

  const addModel = (provider: ModelProvider, model: AvailableModel) => {
    void run(`model-add-${provider.id}-${model.provider_model_id}`, async () => {
      await api.addProviderModel(provider.id, model.provider_model_id)
      await refresh()
      setNotice(t('models.modelAdded'))
    })
  }

  const deleteModel = (model: WorkspaceModel) => {
    if (!window.confirm(t('models.confirmDeleteModel', { name: model.display_name }))) return
    void run(`model-delete-${model.id}`, async () => {
      await api.deleteWorkspaceModel(model.id)
      await refresh()
      setNotice(t('models.modelRemoved'))
    })
  }

  const beginPull = (provider: ModelProvider) => {
    setPullProvider(provider)
    setPullTag('')
    setPullProgress(null)
  }

  const pullModel = async (event: React.FormEvent) => {
    event.preventDefault()
    if (pullProvider === null || !pullTag.trim()) return
    const controller = new AbortController()
    abortController.current = controller
    setBusy('model-pull')
    setError(null)
    setPullProgress({ status: 'starting', progress: 0 })
    try {
      await api.pullOllamaModel(pullProvider.id, pullTag.trim(), setPullProgress, controller.signal)
      if (!controller.signal.aborted) {
        await refresh()
        setNotice(t('models.pullFinished'))
      }
    } catch (pullError) {
      if (!controller.signal.aborted) setError(getErrorMessage(pullError))
    } finally {
      abortController.current = null
      setBusy(null)
    }
  }

  const cancelPull = () => abortController.current?.abort()
  const providerType = form === null ? undefined : providerTypes.find((item) => item.provider_type === form.providerType)
  const providerHintKey = providerType === undefined ? undefined : PROVIDER_HINT_KEYS[providerType.provider_type]
  const visibleAvailableModels = availableModels.filter((item) => `${item.display_name} ${item.provider_model_id}`.toLowerCase().includes(search.toLowerCase()))
  const chatModels = models.filter((model) => model.capabilities.includes('chat'))
  const embeddingModels = models.filter((model) => model.capabilities.includes('embedding'))
  const otherModels = models.filter((model) => !model.capabilities.includes('chat') && !model.capabilities.includes('embedding'))
  const renderModelRows = (entries: WorkspaceModel[]) => (
    <div className="workspace-model-list">
      {entries.map((model) => (
        <div className="workspace-model-row" key={model.id}>
          <div className="workspace-model-icon" aria-hidden="true">{t(model.capabilities.includes('embedding') ? 'catalog.modelIconEmbedding' : 'catalog.modelIconGeneration')}</div>
          <div className="workspace-model-info"><strong>{model.display_name}</strong><span>{model.provider_name} · {model.provider_model_id}</span><div className="workspace-model-badges">{model.capabilities.map((capability) => <span className="badge" key={capability}>{modelCapabilityLabel(t, capability)}</span>)}<span className="badge">{modelStatusLabel(t, model.status)}</span></div></div>
          {typeof model.metadata.size_bytes === 'number' && <span className="model-size">{formatBytes(model.metadata.size_bytes, lang)}</span>}
          <button type="button" className="btn models-delete-button" disabled={busy !== null} onClick={() => deleteModel(model)}>{t('sources.delete')}</button>
        </div>
      ))}
    </div>
  )

  if (loading) return <div className="models-page"><p>{t('models.loading')}</p></div>

  return (
    <div className="models-page">
      <header className="models-heading">
        <div><span className="eyebrow">{t('app.workspace')}</span><h1>{t('models.title')}</h1><p>{t('models.description')}</p></div>
        <button type="button" className="btn btn-primary" onClick={openCreate}>+ {t('models.addProvider')}</button>
      </header>
      {error !== null && form === null && <div className="error page-alert" role="alert">{error}</div>}
      {notice !== null && <div className="success-note models-notice" role="status">{notice}</div>}

      <section className="models-section">
        <div className="models-section-heading"><div><h2>{t('models.connections')}</h2><p>{t('models.connectionsHint')}</p></div></div>
        {providers.length === 0 ? <div className="models-empty">{t('models.noProviders')}</div> : providers.map((provider) => {
          const definition = providerTypes.find((item) => item.provider_type === provider.provider_type)
          const providerModels = models.filter((item) => item.provider_connection_id === provider.id)
          const isPulling = pullProvider?.id === provider.id && busy === 'model-pull'
          return (
            <article className="provider-card" key={provider.id}>
              <div className="provider-card-heading">
                <div><h3>{provider.name}</h3><span className="provider-endpoint">{provider.base_url}</span><div className="provider-card-meta"><span className="badge">{providerCatalogLabel(t, provider.provider_type, definition?.display_name ?? provider.provider_type)}</span><span>{t(provider.has_api_key ? 'models.keyConfigured' : 'models.noKeyNeeded')}</span><span>{t('models.modelCount', { count: String(providerModels.length) })}</span></div></div>
                <div className="provider-actions">
                  <button type="button" className="btn" disabled={busy !== null} onClick={() => testProvider(provider)}>{busy === `provider-test-${provider.id}` ? t('models.checking') : t('models.testConnection')}</button>
                  {definition?.sync_all_models && <button type="button" className="btn" disabled={busy !== null} onClick={() => syncProvider(provider)}>{busy === `provider-sync-${provider.id}` ? t('models.syncing') : t('models.refreshModels')}</button>}
                  {definition?.sync_all_models === false && <button type="button" className="btn" disabled={busy !== null} onClick={() => void browseModels(provider)}>{t('models.browseCatalog')}</button>}
                  {definition?.supports_model_pull && <button type="button" className="btn" disabled={busy !== null} onClick={() => beginPull(provider)}>{t('models.pullModel')}</button>}
                  <button type="button" className="btn" disabled={busy !== null} onClick={() => openEdit(provider)}>{t('sources.edit')}</button>
                  <button type="button" className="btn models-delete-button" disabled={busy !== null} onClick={() => deleteProvider(provider)}>{t('sources.delete')}</button>
                </div>
              </div>
              {definition?.supports_model_pull && isPulling && pullProgress !== null && (
                <div className="models-pull-progress">
                  <div className="models-progress-line"><span>{modelPullStatusLabel(t, pullProgress.status)}</span>{pullProgress.progress !== null && pullProgress.progress !== undefined && <span>{pullProgress.progress}%</span>}</div>
                  <div className="progress-track"><span style={{ width: `${pullProgress.progress ?? 0}%` }} /></div>
                  <button type="button" className="text-button" onClick={cancelPull}>{t('models.cancelPull')}</button>
                </div>
              )}
            </article>
          )
        })}
      </section>

      <section className="models-section">
        <div className="models-section-heading"><div><h2>{t('models.chatModels')}</h2><p>{t('models.chatModelsHint')}</p></div></div>
        {chatModels.length > 0 ? renderModelRows(chatModels) : <div className="models-empty">{t('models.noChatModels')}</div>}
      </section>

      <section className="models-section">
        <div className="models-section-heading"><div><h2>{t('models.embeddingModels')}</h2><p>{t('models.embeddingModelsHint')}</p></div></div>
        {embeddingModels.length > 0 ? renderModelRows(embeddingModels) : <div className="models-empty">{t('models.noEmbeddingModels')}</div>}
      </section>

      {otherModels.length > 0 && <section className="models-section"><div className="models-section-heading"><div><h2>{t('models.otherModels')}</h2><p>{t('models.otherModelsHint')}</p></div></div>{renderModelRows(otherModels)}</section>}

      {form !== null && (
        <div className="modal-overlay">
          <form className="modal models-provider-form" role="dialog" aria-modal="true" onSubmit={(event) => void createProvider(event)}>
            <div className="modal-heading"><h2>{t(editingProvider === null ? 'models.addProviderTitle' : 'models.editProviderTitle')}</h2><button type="button" className="text-button" onClick={() => void finishProviderEdit(true)} aria-label={t(editingProvider === null ? 'common.cancel' : 'catalog.providerClose')}>×</button></div>
            <label>{t('models.providerType')}<select value={form.providerType} disabled={editingProvider !== null} onChange={(event) => {
              const type = providerTypes.find((item) => item.provider_type === event.target.value)
              if (type !== undefined) setForm((current) => current === null ? null : { ...current, providerType: type.provider_type, name: type.display_name, baseUrl: type.default_url })
            }}>{providerTypes.map((type) => <option key={type.provider_type} value={type.provider_type}>{providerCatalogLabel(t, type.provider_type, type.display_name)}</option>)}</select></label>
            <label>{t('models.connectionName')}<input required value={form.name} onKeyDown={blurOnEnter} onBlur={(event) => applyProviderField('name', event.currentTarget.value)} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
            <label>{t('models.apiAddress')}<input required={!providerType?.fixed_url} readOnly={providerType?.fixed_url ?? false} value={form.baseUrl} onKeyDown={blurOnEnter} onBlur={(event) => applyProviderField('baseUrl', event.currentTarget.value)} onChange={(event) => setForm({ ...form, baseUrl: event.target.value })} /></label>
            {providerHintKey !== undefined && (
              <small className="models-form-hint">{t(providerHintKey)}</small>
            )}
            <label>{t('models.apiKey')}{providerType?.requires_api_key ? ' *' : ''}<input type="password" autoComplete="new-password" required={providerType?.requires_api_key === true && editingProvider === null} value={form.apiKey} onKeyDown={blurOnEnter} onBlur={(event) => applyProviderField('apiKey', event.currentTarget.value)} placeholder={editingProvider !== null && editingProvider.has_api_key ? t('models.keyPreserved') : ''} onChange={(event) => setForm({ ...form, apiKey: event.target.value })} /></label>
            {error !== null && <p className="error" role="alert">{error}</p>}
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => void finishProviderEdit()}>{t(editingProvider === null ? 'common.cancel' : 'catalog.providerDone')}</button>
              <button type="button" className="btn" disabled={busy !== null} onClick={() => void testProviderForm()}>{busy === 'provider-test' ? t('models.checking') : t('models.testConnection')}</button>
              {editingProvider === null && <button type="submit" className="btn btn-primary" disabled={busy !== null}>{busy === 'provider-save' ? t('project.uploading') : t('catalog.providerAddConnection')}</button>}
            </div>
          </form>
        </div>
      )}

      {browseProvider !== null && (
        <div className="modal-overlay">
          <section className="modal models-catalog-dialog" role="dialog" aria-modal="true" aria-labelledby="models-catalog-title">
            <div className="modal-heading"><div><h2 id="models-catalog-title">{t('models.browseTitle', { provider: browseProvider.name })}</h2><p>{t('models.browseHint')}</p></div><button type="button" className="text-button" onClick={() => setBrowseProvider(null)} aria-label={t('common.cancel')}>×</button></div>
            <input className="models-search" type="search" value={search} placeholder={t('models.search')} onChange={(event) => setSearch(event.target.value)} />
            <div className="available-model-list">{visibleAvailableModels.map((model) => {
              const added = models.some((entry) => entry.provider_connection_id === browseProvider.id && entry.provider_model_id === model.provider_model_id)
              const key = `model-add-${browseProvider.id}-${model.provider_model_id}`
              return <div className="available-model-row" key={model.provider_model_id}><div><strong>{model.display_name}</strong><span>{model.provider_model_id}</span><div className="workspace-model-badges">{model.capabilities.map((capability) => <span className="badge" key={capability}>{modelCapabilityLabel(t, capability)}</span>)}{typeof model.metadata.context_length === 'number' && <span className="badge">{t('models.contextTokens', { count: String(model.metadata.context_length) })}</span>}</div></div><button type="button" className="btn" disabled={added || busy !== null} onClick={() => addModel(browseProvider, model)}>{busy === key ? t('models.adding') : added ? t('models.added') : t('models.addModel')}</button></div>
            })}{visibleAvailableModels.length === 0 && <p className="models-empty">{t('models.noCatalogResults')}</p>}</div>
          </section>
        </div>
      )}

      {pullProvider !== null && (
        <div className="modal-overlay">
          <form className="modal models-provider-form" role="dialog" aria-modal="true" onSubmit={(event) => void pullModel(event)}>
            <div className="modal-heading"><div><h2>{t('models.pullTitle')}</h2><p>{t('models.pullHint')}</p></div><button type="button" className="text-button" onClick={() => setPullProvider(null)} aria-label={t('common.cancel')}>×</button></div>
            <label>{t('models.modelTag')}<input required value={pullTag} placeholder={t('models.modelTagPlaceholder')} onChange={(event) => setPullTag(event.target.value)} disabled={busy === 'model-pull'} /></label>
            {pullProgress !== null && <div className="models-pull-progress"><div className="models-progress-line"><span>{modelPullStatusLabel(t, pullProgress.status)}</span>{pullProgress.progress !== null && pullProgress.progress !== undefined && <span>{pullProgress.progress}%</span>}</div><div className="progress-track"><span style={{ width: `${pullProgress.progress ?? 0}%` }} /></div></div>}
            <div className="modal-actions"><button type="button" className="btn" onClick={() => setPullProvider(null)}>{t('common.cancel')}</button>{busy === 'model-pull' ? <button type="button" className="btn" onClick={cancelPull}>{t('models.cancelPull')}</button> : <button type="submit" className="btn btn-primary">{t('models.pullModel')}</button>}</div>
          </form>
        </div>
      )}
    </div>
  )
}

function validProviderAddress(value: string): boolean {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password && !url.search && !url.hash
  } catch {
    return false
  }
}

function formatBytes(value: number, language: string): string {
  const units = ['byte', 'kilobyte', 'megabyte', 'gigabyte', 'terabyte']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return new Intl.NumberFormat(language, {
    style: 'unit',
    unit: units[unit],
    unitDisplay: 'short',
    maximumFractionDigits: unit === 0 ? 0 : 1,
  }).format(size)
}
