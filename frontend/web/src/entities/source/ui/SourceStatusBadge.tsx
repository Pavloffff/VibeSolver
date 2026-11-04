import { useT } from '../../../shared/i18n'
import type { TranslationKey } from '../../../shared/i18n'

const STATUS_KEYS: Record<string, TranslationKey> = {
  pending: 'sources.statusPending',
  running: 'sources.statusRunning',
  done: 'sources.statusDone',
  failed: 'sources.statusFailed',
}

interface Props {
  status: string
}

export default function SourceStatusBadge({ status }: Props) {
  const { t } = useT()
  const key = STATUS_KEYS[status]
  return <span className={`badge badge-${status}`}>{key !== undefined ? t(key) : status}</span>
}