import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { I18nProvider, useT } from '../shared/i18n'
import { useLocalizedOutcome } from '../pages/issues-page/ui/useLocalizedOutcome'
import type { Ticket } from '../shared/api/types'
import type { ApiClient } from '../shared/api/client'

function Reader({ ticket, api }: { ticket: Ticket; api: ApiClient }) {
  const { setLang } = useT()
  const { text } = useLocalizedOutcome(ticket, api, true)
  return <><button onClick={() => setLang('zh')}>中文</button><output>{text}</output></>
}

it('shows the saved English answer when the selected translation is unavailable', async () => {
  localStorage.setItem('vibesolver.lang', 'ru')
  const api = { localizeTicketResult: vi.fn().mockResolvedValue({ localized_result: null, english_result: 'Review the service logs.' }) }
  const ticket = { id: 12, status: 'answered', answer: 'Review the service logs.', english_result: 'Review the service logs.' }
  render(<I18nProvider><Reader ticket={ticket as Ticket} api={api as unknown as ApiClient} /></I18nProvider>)
  expect(screen.getByText('Review the service logs.')).toBeInTheDocument()
})

it('uses an English-only translation of a legacy Russian answer when Chinese is unavailable', async () => {
  localStorage.setItem('vibesolver.lang', 'zh')
  const api = { localizeTicketResult: vi.fn().mockResolvedValue({ localized_result: null, english_result: 'Check disk space.' }) }
  const ticket = { id: 21, status: 'answered', answer: 'Проверьте диск.' }
  render(<I18nProvider><Reader ticket={ticket as Ticket} api={api as unknown as ApiClient} /></I18nProvider>)
  expect(await screen.findByText('Check disk space.')).toBeInTheDocument()
  expect(screen.queryByText('Проверьте диск.')).not.toBeInTheDocument()
})

it('switches the saved outcome with the display language without rerunning or retranslating', () => {
  localStorage.setItem('vibesolver.lang', 'en')
  const api = { localizeTicketResult: vi.fn() }
  const ticket = { id: 10, status: 'answered', answer: 'Get all talks.', localized_result: { en: 'Get all talks.', ru: 'Все доклады.', zh: '全部报告。' } }
  render(<I18nProvider><Reader ticket={ticket as Ticket} api={api as unknown as ApiClient} /></I18nProvider>)
  expect(screen.getByText('Get all talks.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button'))
  expect(screen.getByText('全部报告。')).toBeInTheDocument()
  expect(screen.queryByText('Get all talks.')).not.toBeInTheDocument()
  expect(api.localizeTicketResult).not.toHaveBeenCalled()
})

it('loads translations for an old outcome without flashing its original text', async () => {
  localStorage.setItem('vibesolver.lang', 'en')
  const api = { localizeTicketResult: vi.fn().mockResolvedValue({ localized_result: { en: 'Check logs.', ru: 'Проверьте логи.', zh: '查看日志。' } }) }
  const ticket = { id: 11, status: 'escalated', escalate_reason: 'Проверьте логи.' }
  render(<I18nProvider><Reader ticket={ticket as Ticket} api={api as unknown as ApiClient} /></I18nProvider>)
  expect(screen.queryByText('Проверьте логи.')).not.toBeInTheDocument()
  expect(await screen.findByText('Check logs.')).toBeInTheDocument()
  expect(api.localizeTicketResult).toHaveBeenCalledTimes(1)
})

it('keeps an operational failure visible without trying to localize an absent outcome', () => {
  const api = { localizeTicketResult: vi.fn() }
  const ticket = { id: 4, status: 'failed', escalate_reason: 'The configured provider is unavailable.' }
  render(<I18nProvider><Reader ticket={ticket as Ticket} api={api as unknown as ApiClient} /></I18nProvider>)
  expect(screen.getByText(ticket.escalate_reason)).toBeInTheDocument()
  expect(api.localizeTicketResult).not.toHaveBeenCalled()
})
