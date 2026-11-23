import { useEffect, useState } from 'react'
import type { ApiClient } from '../../../shared/api/client'
import type { Ticket } from '../../../shared/api/types'
import { useT } from '../../../shared/i18n'

export function useLocalizedOutcome(ticket: Ticket | null, api: ApiClient, active: boolean) {
  const { lang } = useT()
  const [attempt, setAttempt] = useState(0)
  const [legacy, setLegacy] = useState<{
    ticket: Ticket
    result: Ticket['localized_result']
    english: string | null
  } | null>(null)
  const original = ticket?.status === 'answered' ? ticket.answer : ticket?.escalate_reason
  const isOutcome = ticket?.status === 'answered' || ticket?.status === 'escalated'
  const fetched = legacy !== null && legacy.ticket === ticket
  const translations = ticket?.localized_result ?? (fetched ? legacy.result : null)
  const english = translations?.en ?? ticket?.english_result ?? (fetched ? legacy.english : null)
  useEffect(() => {
    if (!active || !isOutcome || !ticket || !original || ticket.localized_result || fetched || typeof api.localizeTicketResult !== 'function') return
    let current = true
    void api.localizeTicketResult(ticket.id)
      .then(response => { if (current) setLegacy({ ticket, result: response.localized_result, english: response.english_result ?? null }) })
      .catch(() => { if (current) setLegacy({ ticket, result: null, english: null }) })
    return () => { current = false }
  }, [api, ticket, original, fetched, active, attempt, isOutcome])
  const preferred = translations?.[lang]
  const text = !isOutcome ? original : preferred ?? english ?? (typeof api.localizeTicketResult === 'function' ? null : original)
  return {
    text,
    displayLanguage: !isOutcome ? undefined : preferred || !english ? lang : 'en',
    unavailable: fetched && !text,
    retry: () => { setLegacy(null); setAttempt(value => value + 1) },
  }
}
