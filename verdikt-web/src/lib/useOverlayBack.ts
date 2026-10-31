import { useEffect, useRef } from 'react';
import { registerOverlayBack } from './overlayBack';

/**
 * Wire an overlay to the browser back button. `mediaQuery` limits the behavior
 * to the viewports where the overlay is modal (e.g. the drawer exists only on
 * phones): outside it the overlay never enters the history stack.
 */
export function useOverlayBack(open: boolean, close: () => void, mediaQuery?: string): void {
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    if (!open) return;
    if (mediaQuery && !window.matchMedia(mediaQuery).matches) return;
    return registerOverlayBack(() => closeRef.current());
  }, [open, mediaQuery]);
}
