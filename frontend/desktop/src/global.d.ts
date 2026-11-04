import type { VibesolverBridge } from './bridge-types';

declare global {
  interface Window {
    __VIBESOLVER_API_URL__?: string;
    vibesolver?: VibesolverBridge;
  }
}

export {};
