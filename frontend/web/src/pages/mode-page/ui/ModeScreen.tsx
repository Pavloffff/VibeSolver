import { useState } from 'react'
import { ApiClient, getErrorMessage } from '../../../shared/api/client'
import { DEFAULT_SERVER_URL } from '../../../shared/config'
import { useT } from '../../../shared/i18n'
import { saveSettings } from '../../../shared/state/settings'
import type { AppMode, AppSettings } from '../../../shared/state/settings'

type CheckState = 'idle' | 'checking' | 'ok' | 'err'

function cardClass(selected: boolean): string {
  return selected ? 'card card-selected' : 'card'
}

interface Props {
  onDone: (settings: AppSettings) => void
}

export default function ModeScreen({ onDone }: Props) {
  const { t } = useT()
  const [mode, setMode] = useState<AppMode>('local')
  const [serverUrl, setServerUrl] = useState(DEFAULT_SERVER_URL)
  const [checkState, setCheckState] = useState<CheckState>('idle')
  const [checkError, setCheckError] = useState<string | null>(null)

  const checkConnection = async () => {
    setCheckState('checking')
    setCheckError(null)
    try {
      await new ApiClient(() => serverUrl).checkHealth()
      setCheckState('ok')
    } catch (error) {
      setCheckError(getErrorMessage(error))
      setCheckState('err')
    }
  }

  const start = () => {
    const settings: AppSettings = {
      mode,
      serverUrl: mode === 'local' ? DEFAULT_SERVER_URL : serverUrl.trim(),
    }
    saveSettings(settings)
    onDone(settings)
  }

  return (
    <div className="mode-screen">
      <h1>VibeSolver</h1>
      <p>{t('modeScreen.prompt')}</p>
      <div className="cards">
        <div
          className={cardClass(mode === 'local')}
          onClick={() => {
            setMode('local')
            setCheckState('idle')
            setCheckError(null)
          }}
        >
          <h2>{t('common.local')}</h2>
          <p>{t('modeScreen.localDescription')}</p>
        </div>
        <div
          className={cardClass(mode === 'remote')}
          onClick={() => {
            setMode('remote')
          }}
        >
          <h2>{t('common.remote')}</h2>
          <p>{t('modeScreen.remoteDescription')}</p>
          <input
            type="text"
            value={serverUrl}
            placeholder={t('common.serverUrl')}
            onChange={(event) => {
              setServerUrl(event.target.value)
            }}
          />
          <button
            type="button"
            className="btn"
            disabled={checkState === 'checking'}
            onClick={(event) => {
              event.stopPropagation()
              void checkConnection()
            }}
          >
            {t('common.checkConnection')}
          </button>
          {checkState === 'ok' && <span className="ok">{t('common.connectionOk')}</span>}
          {checkState === 'err' && checkError !== null && <span className="error">{checkError}</span>}
        </div>
      </div>
      <button type="button" className="btn btn-primary btn-large" onClick={start}>
        {t('modeScreen.start')}
      </button>
    </div>
  )
}
