import { useCallback, useEffect, useRef, useState } from 'react'
import { getErrorMessage } from '../../../shared/api/client'
import type { ApiClient } from '../../../shared/api/client'
import type { ImportStatus } from '../../../entities/source'

interface Props {
  api: ApiClient
  onFinished: () => void
  onError: (message: string) => void
}

export function useImportRunner({ api, onFinished, onError }: Props) {
  const [imports, setImports] = useState<Record<number, ImportStatus>>({})
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  useEffect(() => {
    const timerMap = timers.current
    return () => {
      for (const timer of timerMap.values()) {
        clearTimeout(timer)
      }
      timerMap.clear()
    }
  }, [])

  const pollImport = useCallback(
    async (id: number) => {
      try {
        const status = await api.getImportStatus(id)
        setImports((prev) => ({ ...prev, [id]: status }))
        if (status.status === 'pending' || status.status === 'running') {
          const timer = setTimeout(() => {
            void pollImport(id)
          }, 2000)
          timers.current.set(id, timer)
        } else {
          timers.current.delete(id)
          onFinished()
        }
      } catch (requestError) {
        onError(getErrorMessage(requestError))
      }
    },
    [api, onFinished, onError],
  )

  const startImport = useCallback(
    async (id: number) => {
      try {
        await api.startImport(id)
        setImports((prev) => ({ ...prev, [id]: { status: 'pending', progress: 0, error: null } }))
        const timer = setTimeout(() => {
          void pollImport(id)
        }, 2000)
        timers.current.set(id, timer)
      } catch (requestError) {
        onError(getErrorMessage(requestError))
      }
    },
    [api, pollImport, onError],
  )

  return { imports, startImport }
}