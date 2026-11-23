import type { ConfigField } from '../api/types'
import type { TranslationKey } from './types'

type Translate = (key: TranslationKey) => string

const connectorLabels = new Map<string, TranslationKey>([
  ['git', 'catalog.connectorGit'],
  ['local_folder', 'catalog.connectorLocalFolder'],
  ['archive', 'catalog.connectorArchive'],
  ['hg', 'catalog.connectorMercurial'],
  ['svn', 'catalog.connectorSubversion'],
])

export function connectorLabel(t: Translate, type: string): string {
  const key = connectorLabels.get(type)
  return key === undefined ? type : t(key)
}

interface ConnectorFieldLabels {
  label: TranslationKey
  hint?: TranslationKey
}

const repositoryField: ConnectorFieldLabels = { label: 'catalog.repositoryUrl' }
const connectorFields = new Map<string, ConnectorFieldLabels>([
  ['git:url', repositoryField],
  ['hg:url', repositoryField],
  ['svn:url', repositoryField],
  ['git:token_ref', { label: 'catalog.gitToken', hint: 'catalog.gitTokenHint' }],
  ['archive:upload_key', { label: 'sourceForm.archiveFile', hint: 'sourceForm.archiveHint' }],
])

export function connectorFieldLabels(t: Translate, type: string, field: ConfigField) {
  const labels = connectorFields.get(`${type}:${field.name}`)
  return {
    label: labels ? t(labels.label) : field.label,
    hint: labels?.hint ? t(labels.hint) : field.hint,
  }
}

export function providerCatalogLabel(t: Translate, type: string, fallback: string): string {
  return type === 'kimi' ? t('catalog.kimi') : fallback
}

const capabilityLabels = new Map<string, TranslationKey>([
  ['chat', 'models.capabilityChat'],
  ['embedding', 'models.capabilityEmbedding'],
])

export function modelCapabilityLabel(t: Translate, capability: string): string {
  const key = capabilityLabels.get(capability)
  return key === undefined ? capability : t(key)
}

const modelStatusLabels = new Map<string, TranslationKey>([
  ['installed', 'models.statusInstalled'],
  ['available', 'models.statusRemote'],
  ['pulling', 'models.statusPulling'],
  ['error', 'models.statusError'],
  ['cancelled', 'models.statusCancelled'],
])

export function modelStatusLabel(t: Translate, status: string): string {
  return t(modelStatusLabels.get(status) ?? 'catalog.modelStatusUnknown')
}

const pullStatusLabels = new Map<string, TranslationKey>([
  ['starting', 'catalog.pullStarting'],
  ['pulling manifest', 'catalog.pullManifest'],
  ['verifying sha256 digest', 'catalog.pullVerifying'],
  ['writing manifest', 'catalog.pullWriting'],
  ['removing any unused layers', 'catalog.pullCleaning'],
  ['success', 'catalog.pullSuccess'],
  ['complete', 'catalog.pullSuccess'],
  ['error', 'models.statusError'],
  ['cancelled', 'models.statusCancelled'],
])

export function modelPullStatusLabel(t: Translate, status: string | null | undefined): string {
  const key = status == null ? undefined : pullStatusLabels.get(status.trim().toLowerCase())
  return t(key ?? 'models.statusPulling')
}
