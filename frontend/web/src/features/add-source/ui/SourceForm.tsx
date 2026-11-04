import { useEffect, useState } from 'react'
import { getApiClient, getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import type { ConnectorInfo } from '../../../entities/source'
import { useT } from '../../../shared/i18n'

interface Props {
  api?: ApiClient
  onCreated: () => void
  onClose: () => void
}

export default function SourceForm({ api = getApiClient(), onCreated, onClose }: Props) {
  const { t } = useT()
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([])
  const [type, setType] = useState('')
  const [name, setName] = useState('')
  const [config, setConfig] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .listConnectors()
      .then((list) => {
        if (!cancelled) {
          setConnectors(list)
        }
      })
      .catch((requestError: unknown) => {
        if (!cancelled) {
          setError(getErrorMessage(requestError))
        }
      })
    return () => {
      cancelled = true
    }
  }, [api])

  const selected = connectors.find((connector) => connector.type === type) ?? null

  const setFieldValue = (fieldName: string, value: string) => {
    setConfig((prev) => ({ ...prev, [fieldName]: value }))
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!type) {
      setError(t('errors.selectType'))
      return
    }
    if (!name.trim()) {
      setError(t('errors.enterName'))
      return
    }
    const fields = selected !== null ? selected.config_schema.fields : []
    for (const field of fields) {
      if (field.required && !(config[field.name] ?? '').trim()) {
        setError(t('errors.fillField', { field: field.label }))
        return
      }
    }
    setSaving(true)
    try {
      await api.createSource(type, name.trim(), config)
      onCreated()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)}>
      <label>
        {t('sourceForm.typeLabel')}
        <select
          value={type}
          onChange={(event) => {
            setType(event.target.value)
            setConfig({})
          }}
        >
          <option value="">{t('sourceForm.typePlaceholder')}</option>
          {connectors.map((connector) => (
            <option key={connector.type} value={connector.type} disabled={!connector.ready}>
              {connector.type}
              {connector.ready ? '' : ` (${t('sourceForm.connectorUnavailable')})`}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('sourceForm.nameLabel')}
        <input
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t('sourceForm.namePlaceholder')}
        />
      </label>
      {selected !== null &&
        selected.config_schema.fields.map((field) => (
          <label key={field.name}>
            {field.required ? `${field.label} *` : field.label}
            {field.kind === 'password' ? (
              <input
                type="password"
                value={config[field.name] ?? ''}
                onChange={(event) => setFieldValue(field.name, event.target.value)}
              />
            ) : (
              <input
                type="text"
                value={config[field.name] ?? ''}
                placeholder={field.kind === 'path' ? t('sourceForm.pathPlaceholder') : undefined}
                onChange={(event) => setFieldValue(field.name, event.target.value)}
              />
            )}
          </label>
        ))}
      {error !== null && <p className="error">{error}</p>}
      <div className="modal-actions">
        <button type="button" className="btn" onClick={onClose}>
          {t('common.cancel')}
        </button>
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {t('sourceForm.submit')}
        </button>
      </div>
    </form>
  )
}
