import { SERVER_URL_STORAGE_KEY } from './state/settings'

declare global {
  interface Window {
    __VIBESOLVER_API_URL__?: string
  }
}

export const DEFAULT_SERVER_URL = 'http://localhost:8000'

export function getApiBaseUrl(): string {
  if (typeof window !== 'undefined' && window.__VIBESOLVER_API_URL__) {
    return window.__VIBESOLVER_API_URL__
  }
  const stored = localStorage.getItem(SERVER_URL_STORAGE_KEY)
  if (stored) {
    return stored
  }
  return DEFAULT_SERVER_URL
}
