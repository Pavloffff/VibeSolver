import type { VibesolverBridge } from '../bridge'

export function hasNativeFolderDialog(): boolean {
  const bridge = typeof window !== 'undefined' ? window.vibesolver : undefined
  return bridge !== undefined && typeof bridge.selectFolder === 'function'
}

export async function selectFolder(): Promise<string | null> {
  const bridge: VibesolverBridge | undefined =
    typeof window !== 'undefined' ? window.vibesolver : undefined
  if (bridge !== undefined && typeof bridge.selectFolder === 'function') {
    return bridge.selectFolder()
  }
  return null
}