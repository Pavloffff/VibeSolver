import { useEffect, useState } from 'react'
import { getApiClient, getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import type { ConfigField, ConnectorInfo } from '../../../entities/source'
import { useT } from '../../../shared/i18n'
import { selectFolder } from '../../../shared/api/folderPicker'
import { hasNativeFolderDialog } from '../../../shared/api/folderPicker'

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
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
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
    setFieldErrors((prev) => ({ ...prev, [fieldName]: '' }))
  }

  const pickFolder = async (field: ConfigField) => {
    if (hasNativeFolderDialog()) {
      const picked = await selectFolder()
      if (picked !== null) {
        setFieldValue(field.name, picked)
      }
      return
    }
    setFieldErrors((prev) => ({ ...prev, [field.name]: t('errors.browserNoPath') }))
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
    const missing: Record<string, string> = {}
    for (const field of fields) {
      if (field.required && !(config[field.name] ?? '').trim()) {
        missing[field.name] =
          field.kind === 'folder' ? t('errors.chooseFolder') : t('errors.fillField', { field: field.label })
      }
    }
    if (Object.keys(missing).length > 0) {
      setFieldErrors(missing)
      return
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

  const renderField = (field: ConfigField) => {
    const value = config[field.name] ?? ''
    const fieldError = fieldErrors[field.name] ?? ''
    const commonProps = {
      value,
      onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
        setFieldValue(field.name, event.target.value),
    }
    let control
    if (field.kind === 'password') {
      control = <input type="password" {...commonProps} />
    } else if (field.kind === 'folder') {
      control = (
        <span className="folder-picker">
          <input
            type="text"
            {...commonProps}
            placeholder={t('sourceForm.folderOrServer')}
            className={fieldError !== '' ? 'input-error' : undefined}
          />
          {hasNativeFolderDialog() && (
            <button
              type="button"
              className="btn"
              onClick={(event) => {
                event.preventDefault()
                void pickFolder(field)
              }}
            >
              {t('sourceForm.browse')}
            </button>
          )}
        </span>
      )
    } else {
      control = (
        <input
          type="text"
          {...commonProps}
          placeholder={field.placeholder ?? t('sourceForm.pathPlaceholder')}
        />
      )
    }
    return (
      <label key={field.name}>
        {field.required ? `${field.label} *` : field.label}
        {control}
        {field.hint != null && field.hint !== '' && <small className="hint">{field.hint}</small>}
        {fieldError !== '' && <small className="error">{fieldError}</small>}
      </label>
    )
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
            setFieldErrors({})
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
      {selected !== null && selected.config_schema.fields.map(renderField)}
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