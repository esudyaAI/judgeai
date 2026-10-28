import { useEffect, useRef } from 'react';
import type { CaseSummary } from '../api/types';
import { Icon } from '../components/Icon';
import { LogoMark } from '../components/Logo';
import { Link } from '../router';

interface Props {
  cases: CaseSummary[];
  username: string;
  activeId: string | null;
  thinking: boolean;
  settingsActive: boolean;
  /** Mobile only: drawer state (on desktop the sidebar is always visible). */
  open: boolean;
  onClose: () => void;
  onNew: () => void;
  onPick: (c: CaseSummary) => void;
  onSettings: () => void;
}

export function Sidebar({ username, cases, activeId, thinking, settingsActive, open, onClose, onNew, onPick, onSettings }: Props) {
  const asideRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    asideRef.current?.querySelector<HTMLElement>('button, a, input')?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const groups: { title: string; items: CaseSummary[] }[] = [];
  for (const c of cases) {
    const last = groups[groups.length - 1];
    if (last && last.title === c.group) last.items.push(c);
    else groups.push({ title: c.group, items: [c] });
  }

  return (
    <>
      {open && <div className="cab-scrim" onClick={onClose} aria-hidden="true" />}
      <aside ref={asideRef} className={`cab-side ${open ? 'open' : ''}`} aria-label="Дела">
        <Link href="/" className="cab-brand">
          <LogoMark size={30} color="#141414" />
          <span>Цифровой судья</span>
        </Link>
        <button type="button" className="btn btn-ink btn-md" onClick={onNew}>
          <Icon name="plus" size={18} strokeWidth={2} />
          Новое дело
        </button>
        <label className="cab-search">
          <span className="sr-only">Поиск по делам</span>
          <Icon name="search" size={16} strokeWidth={2} color="#707070" className="cab-search-icon" />
          {/* TODO(api): filter cases */}
          <input type="search" placeholder="Поиск по делам" />
        </label>

        <nav className="cab-list" aria-label="Список дел">
          {groups.map((g) => (
            <div key={g.title} className="cab-group">
              <span className="cab-group-title">{g.title}</span>
              {g.items.map((c) => {
                const on = c.id === activeId;
                const status = on && thinking ? 'busy' : c.status;
                return (
                  <button key={c.id} type="button" className={`cab-row ${on ? 'on' : ''}`} aria-current={on ? 'page' : undefined} onClick={() => onPick(c)}>
                    <span className={`cab-dot ${status}`} aria-hidden="true" />
                    <span className="cab-row-text">
                      <span className="cab-row-title">{c.title}</span>
                      <span className="cab-row-meta">{on && thinking ? 'Идёт анализ' : c.meta}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <button type="button" className={`cab-row cab-profile ${settingsActive ? 'on' : ''}`} onClick={onSettings} aria-label="Настройки аккаунта">
          <span className="avatar" aria-hidden="true">
            {username.slice(0, 2).toUpperCase()}
          </span>
          <span className="cab-row-text">
            <span className="cab-row-title">{username}</span>
            <span className="cab-row-meta">Личный кабинет</span>
          </span>
          <Icon name="gear" size={18} color="#707070" />
        </button>
      </aside>
    </>
  );
}
