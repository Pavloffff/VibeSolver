import { useEffect, useState } from 'react'
import ObservationInput from '../../features/ui-observation/ui/ObservationInput'
import { getApiClient, getErrorMessage, type ApiClient } from '../../shared/api/client'
import type { TicketBrief } from '../../shared/api/types'
import { useT } from '../../shared/i18n'
import './experiments.css'

export default function ExperimentsPage({ projectId, api = getApiClient() }: { projectId: number; api?: ApiClient }) {
  const { t } = useT()
  const [tickets, setTickets] = useState<TicketBrief[] | null>(null)
  const [ticketId, setTicketId] = useState<number | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setTickets(null)
    setTicketId(null)
    setError('')
    void api.listTickets(projectId)
      .then(items => { if (active) setTickets(items) })
      .catch((reason: unknown) => { if (active) setError(getErrorMessage(reason)) })
    return () => { active = false }
  }, [projectId, api])

  return <section className="experiments-page">
    <h1>{t('settings.experimental')}</h1>
    <section className="project-card experiment-card">
      <h2>{t('issues.observationTitle')}</h2>
      {error && <p className="error" role="alert">{error}</p>}
      {tickets && (tickets.length ? <>
        <label>{t('experimental.observationTicket')}
          <select value={ticketId ?? ''} onChange={event => setTicketId(Number(event.target.value) || null)}>
            <option value="">{t('experimental.pickTicket')}</option>
            {tickets.map(ticket => <option key={ticket.id} value={ticket.id}>#{ticket.id} · {ticket.title}</option>)}
          </select>
        </label>
        {ticketId !== null && <ObservationInput key={ticketId} ticketId={ticketId} api={api} />}
      </> : <p>{t('experimental.emptyTickets')}</p>)}
      {tickets === null && !error && <p role="status">{t('experimental.loadingTickets')}</p>}
    </section>
  </section>
}
