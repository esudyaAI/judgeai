import { useEffect, useLayoutEffect, useId, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence } from 'motion/react';
import { PresenceSurface } from '../components/PresenceSurface';
import { actionMenuPosition } from './actionMenuPosition';

interface Action {label: string; icon: ReactNode; disabled?: boolean; danger?: boolean; run: () => void}

export function ActionMenu({label, children, actions, className = '', placement = 'auto', matchTriggerWidth = false}: {label: string; children: ReactNode; actions: Action[]; className?: string; placement?: 'auto' | 'above'; matchTriggerWidth?: boolean}) {
  const [position, setPosition] = useState<ReturnType<typeof actionMenuPosition> | null>(null);
  const menuId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const close = (focus = false) => { setPosition(null); if (focus) trigger.current?.focus(); };
  const isOpen = position !== null;
  const locate = () => {
    const rect = trigger.current?.getBoundingClientRect();
    return rect ? actionMenuPosition(rect, {width:window.innerWidth,height:window.innerHeight}, menu.current?.offsetHeight || actions.length * 44 + 14, placement, matchTriggerWidth) : null;
  };
  useLayoutEffect(() => {
    if (isOpen) setPosition(locate());
  }, [isOpen, actions.length, placement, matchTriggerWidth]);
  useEffect(() => {
    if (!isOpen) return;
    menu.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus({preventScroll:true});
    const outside = (event: PointerEvent) => { if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) setPosition(null); };
    const dismiss = () => setPosition(null);
    // Search results can change the list scroll offset while the menu is open.
    const reposition = () => setPosition(locate());
    document.addEventListener('pointerdown', outside);
    window.addEventListener('resize', dismiss);
    window.addEventListener('scroll', reposition, true);
    return () => { document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', dismiss); window.removeEventListener('scroll', reposition, true); };
  }, [isOpen]);
  const open = () => {
    if (position) { close(true); return; }
    setPosition(locate());
  };
  return <>
    <button ref={trigger} type="button" className={className} aria-label={label} title={label} aria-haspopup="menu" aria-controls={isOpen ? menuId : undefined} aria-expanded={!!position} onClick={open} onKeyDown={event => { if (event.key === 'ArrowDown') { event.preventDefault(); open(); } }}>{children}</button>
    {typeof document !== 'undefined' && createPortal(<AnimatePresence>{position && <PresenceSurface key="menu" ref={menu} id={menuId} data-menu-owner={trigger.current?.closest('.cab-side') ? 'sidebar' : undefined} role="menu" aria-label={label} className="cab-action-menu" style={position} onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); }
      if (event.key === 'Tab') { event.preventDefault(); close(true); }
      const items = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || []);
      const index = items.indexOf(document.activeElement as HTMLButtonElement);
      if (['ArrowDown','ArrowUp','Home','End'].includes(event.key) && items.length) {
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items[next].focus();
      }
    }}>{actions.map(action => <button role="menuitem" key={action.label} type="button" disabled={action.disabled} className={action.danger ? 'danger' : ''} onClick={() => { close(true); action.run(); }}>{action.icon}<span>{action.label}</span></button>)}</PresenceSurface>}</AnimatePresence>, document.body)}
  </>;
}
