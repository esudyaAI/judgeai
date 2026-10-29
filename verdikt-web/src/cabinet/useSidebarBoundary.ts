import {useEffect, type RefObject} from 'react';
import {acquireInert} from './inertLayers';
const focusables = 'button:not(:disabled), a[href], input:not(:disabled), [tabindex="0"]';
/** The drawer and its portalled menu form one focus boundary on small screens. */
export function useSidebarBoundary(ref: RefObject<HTMLElement | null>, open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const aside = ref.current;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const media = window.matchMedia('(max-width: 760px)');
    const main = aside?.parentElement?.querySelector<HTMLElement>('.cab-main');
    let release: (() => void) | undefined;
    const update = () => {
      if (main && media.matches && !release) release = acquireInert(main);
      else if (!media.matches && release) { release(); release = undefined; }
    };
    update(); media.addEventListener('change',update);
    aside?.querySelector<HTMLElement>(focusables)?.focus();
    const key = (event: KeyboardEvent) => {
      if (document.querySelector('dialog[open], .document-panel[aria-modal="true"]')) return;
      if (event.key === 'Escape') { event.preventDefault(); onClose(); return; }
      if (!media.matches || event.key !== 'Tab') return;
      const portal = document.querySelector<HTMLElement>('[data-menu-owner="sidebar"]:not([inert])');
      const items = [...Array.from(aside?.querySelectorAll<HTMLElement>(focusables) || []), ...Array.from(portal?.querySelectorAll<HTMLElement>(focusables) || [])].filter(el=>el.getClientRects().length);
      if (!items.length) return;
      const first=items[0], last=items[items.length-1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !items.includes(document.activeElement as HTMLElement))) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown',key);
    return () => {
      media.removeEventListener('change',update); window.removeEventListener('keydown',key);
      release?.();
      if (previous?.isConnected && !previous.closest('[inert]')) previous.focus();
    };
  }, [ref,open,onClose]);
}
