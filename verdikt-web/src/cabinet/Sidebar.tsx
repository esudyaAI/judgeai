import { useEffect, useRef } from 'react';
import type { Profile } from '../api/client';
import { useChatSearch } from './useChatSearch';
import type { CaseSummary } from '../api/types';
import { Icon } from '../components/Icon';
import { LogoMark } from '../components/Logo';
import { Link } from '../router';

interface Props {
  cases: CaseSummary[];
  username: string;
  profile?: Profile | null;
  activeId: string | null;
  thinking: boolean;
  settingsActive: boolean;
  /** Mobile only: drawer state (on desktop the sidebar is always visible). */
  open: boolean;
  onClose: () => void;
  onDelete: (chat: CaseSummary) => void;
  deletingId: string | null;
  deleteError: string;
  deleteNotice: string;
  onNew: () => void;
  onPick: (c: CaseSummary) => void;
  onSettings: () => void;
}

export function Sidebar({ onDelete, deletingId, deleteError, deleteNotice, username, profile, cases, activeId, thinking, settingsActive, open, onClose, onNew, onPick, onSettings }: Props) {
  const {query, setQuery, results, searching, searchError, retry: retrySearch} = useChatSearch(cases);
  const asideRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    asideRef.current?.querySelector<HTMLElement>('button, a, input')?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const groups: { title: string; items: CaseSummary[] }[] = [];
  for (const c of query.trim() ? results : cases) {
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
          <input type="search" placeholder="Поиск по чатам" maxLength={200} value={query} onChange={e => setQuery(e.target.value)} />
        </label>

        {query && <button type="button" className="btn btn-soft btn-xs" onClick={() => setQuery('')}>Сбросить поиск</button>}
        {deleteError && <p className="cab-search-status" role="alert">{deleteError}</p>}
        {deleteNotice && <p className="cab-search-status" role="status">{deleteNotice}</p>}
        <nav className="cab-list" aria-label="Список дел" aria-busy={searching}>
          {searching && <p className="cab-search-status shimmer" role="status">Ищем по названию, сообщениям и файлам…</p>}
          {searchError && <div className="cab-search-status" role="alert">{searchError}<button type="button" onClick={retrySearch}>Повторить</button></div>}
          {query.trim() && !searching && !searchError && !results.length && <p className="cab-search-status" role="status">Ничего не найдено. Попробуйте другой запрос.</p>}
          {groups.map((g) => (
            <div key={g.title} className="cab-group">
              <span className="cab-group-title">{g.title}</span>
              {g.items.map((c) => {
                const on = c.id === activeId;
                const status = on && thinking ? 'busy' : c.status;
                return (
                  <div key={c.id} className={`cab-chat-row ${on ? 'on' : ''}`}>
                  <button type="button" data-loading={status === 'busy' || undefined} className={`cab-row ${on ? 'on' : ''}`} aria-current={on ? 'page' : undefined} onClick={() => onPick(c)}>
                    <span className={`cab-dot ${status}`} aria-hidden="true" />
                    <span className="cab-row-text">
                      <span className="cab-row-title">{c.title}</span>
                      <span className="cab-row-meta">{on && thinking ? 'Идёт анализ' : c.meta}</span>
                    </span>
                  </button>
                  <button type="button" className="cab-delete" aria-label={`Удалить чат «${c.title}»`}
                    title={status === 'busy' ? 'Дождитесь завершения анализа' : 'Удалить чат'}
                    disabled={deletingId !== null || status === 'busy'}
                    aria-busy={deletingId === c.id || undefined} onClick={() => onDelete(c)}>
                    <Icon name="trash" size={17} />
                  </button>
                  </div>
                );
              })}
            </div>
          ))}
        </nav>

        <button type="button" className={`cab-row cab-profile ${settingsActive ? 'on' : ''}`} onClick={onSettings} aria-label="Настройки аккаунта">
          <span className="avatar" aria-hidden="true">
            {profile?.avatar ? <img src={profile.avatar} alt="" /> : (profile?.firstName || username).slice(0, 2).toUpperCase()}
          </span>
          <span className="cab-row-text">
            <span className="cab-row-title">{[profile?.firstName, profile?.lastName].filter(Boolean).join(' ') || username}</span>
            <span className="cab-row-meta">Личный кабинет</span>
          </span>
          <Icon name="gear" size={18} color="#707070" />
        </button>
      </aside>
    </>
  );
}
