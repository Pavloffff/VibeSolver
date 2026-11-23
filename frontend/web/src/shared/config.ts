import { SERVER_URL_STORAGE_KEY } from './state/settings'

declare global {
  interface Window {
    __VIBESOLVER_API_URL__?: string
  }
}

export function getLocalServerUrl(): string {
  return window.vibesolver?.localServerUrl || window.__VIBESOLVER_API_URL__ || window.location.origin
}

export function getApiBaseUrl(): string {
  if (window.vibesolver && window.__VIBESOLVER_API_URL__) {
    return window.__VIBESOLVER_API_URL__
  }
  const stored = localStorage.getItem(SERVER_URL_STORAGE_KEY)
  if (stored) {
    return stored
  }
  return getLocalServerUrl()
}
