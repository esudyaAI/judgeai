import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

interface Action {label: string; icon: ReactNode; disabled?: boolean; danger?: boolean; run: () => void}

export function ActionMenu({label, children, actions, className = ''}: {label: string; children: ReactNode; actions: Action[]; className?: string}) {
  const [position, setPosition] = useState<{top:number;left:number} | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const close = (focus = false) => { setPosition(null); if (focus) trigger.current?.focus(); };
  const isOpen = position !== null;
  const locate = () => {
    const rect = trigger.current?.getBoundingClientRect();
    return rect ? {left:Math.max(8, Math.min(rect.right - 210,window.innerWidth - 218)),top:Math.max(8, Math.min(rect.bottom + 6,window.innerHeight - actions.length * 44 - 28))} : null;
  };
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
    <button ref={trigger} type="button" className={className} aria-label={label} title={label} aria-haspopup="menu" aria-expanded={!!position} onClick={open} onKeyDown={event => { if (event.key === 'ArrowDown') { event.preventDefault(); open(); } }}>{children}</button>
    {position && createPortal(<div ref={menu} role="menu" aria-label={label} className="cab-action-menu" style={position} onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); }
      if (event.key === 'Tab') close();
      const items = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || []);
      const index = items.indexOf(document.activeElement as HTMLButtonElement);
      if (['ArrowDown','ArrowUp','Home','End'].includes(event.key) && items.length) {
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items[next].focus();
      }
    }}>{actions.map(action => <button role="menuitem" key={action.label} type="button" disabled={action.disabled} className={action.danger ? 'danger' : ''} onClick={() => { close(true); action.run(); }}>{action.icon}<span>{action.label}</span></button>)}</div>, document.body)}
  </>;
}
