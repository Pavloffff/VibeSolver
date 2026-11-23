import { t, type Lang, type TranslationKey } from '../i18n'
import { apiErrorsEN } from '../i18n/apiErrors.en'

const apiMessages = new Map(Object.entries(apiErrorsEN).map(([key, message]) =>
  [message.toLowerCase(), key as keyof typeof apiErrorsEN] as const,
))

const fieldLabels: Partial<Record<string, TranslationKey>> = {
  name: 'sourceForm.nameLabel', title: 'issues.titleLabel', description: 'issues.descriptionLabel',
  profile_id: 'solver.profile', comment: 'issueWorkspace.comment', api_key: 'models.apiKey',
}

function validationMessage(lang: Lang, issue: unknown): string {
  if (!issue || typeof issue !== 'object') return t(lang, 'errors.invalidResponse')
  const parts = 'loc' in issue && Array.isArray(issue.loc) ? issue.loc : []
  const path = parts.filter(part => typeof part === 'string' || typeof part === 'number')
  if (typeof path[0] === 'string' && ['body', 'query', 'path', 'header'].includes(path[0])) path.shift()
  const name = path.length === 1 ? path[0] : undefined
  const fieldKey = typeof name === 'string' && Object.hasOwn(fieldLabels, name) ? fieldLabels[name] : undefined
  const field = fieldKey ? t(lang, fieldKey) : path.join('.') || t(lang, 'errors.request')
  const type = 'type' in issue ? issue.type : undefined
  if (type === 'missing') return t(lang, 'errors.fieldRequired', { field })
  const ctx = 'ctx' in issue && issue.ctx && typeof issue.ctx === 'object' ? issue.ctx : null
  if (type === 'string_too_long' && ctx && 'max_length' in ctx) {
    return t(lang, 'errors.fieldMaxLength', { field, limit: String(ctx.max_length) })
  }
  if (type === 'string_too_short' && ctx && 'min_length' in ctx) {
    return t(lang, 'errors.fieldMinLength', { field, limit: String(ctx.min_length) })
  }
  if (type === 'value_error' && 'msg' in issue && typeof issue.msg === 'string') {
    const message = issue.msg.replace(/^Value error, /, '')
    const key = apiMessages.get(message.toLowerCase())
    return `${field}: ${key ? t(lang, key) : message}`
  }
  return t(lang, 'errors.fieldInvalid', { field })
}

export function responseErrorMessage(lang: Lang, status: number, body: string): string {
  let detail: unknown
  try {
    detail = JSON.parse(body)?.detail
  } catch {
    detail = body
  }
  const message = typeof detail === 'string' ? detail : body
  const key = apiMessages.get(message.toLowerCase())
  const localized = key ? t(lang, key) : message
  return t(lang, 'errors.httpError', {
    status: String(status),
    body: Array.isArray(detail) ? detail.map(issue => validationMessage(lang, issue)).join('\n') : localized,
  })
}
