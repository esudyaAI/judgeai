import { useRef } from 'react';
import { motion } from 'motion/react';
import type { Profile } from '../api/client';
import { useChatSearch } from './useChatSearch';
import type { CaseSummary } from '../api/types';
import { Icon } from '../components/Icon';
import { LogoMark } from '../components/Logo';
import { ActionMenu } from './ActionMenu';
import { Link } from '../router';
import {useSidebarBoundary} from './useSidebarBoundary';
import {StateNotice} from '../components/UiState';

interface Props {
  cases: CaseSummary[];
  listLoading?: boolean;
  listError?: string;
  onRetryList?: () => void;
  signingOut?: boolean;
  username: string;
  profile?: Profile | null;
  activeId: string | null;
  thinking: boolean;
  settingsActive: boolean;
  /** Mobile only: drawer state (on desktop the sidebar is always visible). */
  open: boolean;
  onClose: () => void;
  onDelete: (chat: CaseSummary) => void;
  onPin: (chat: CaseSummary) => void;
  pinningId: string | null;
  pinError: string;
  collapsed: boolean;
  onSignOut: () => void;
  deletingId: string | null;
  deleteError: string;
  deleteNotice: string;
  onNew: () => void;
  onPick: (c: CaseSummary) => void;
  onSettings: () => void;
}

export function Sidebar({ listLoading = false, listError = '', onRetryList, signingOut = false, onPin, pinningId, pinError, collapsed, onSignOut, onDelete, deletingId, deleteError, deleteNotice, username, profile, cases, activeId, thinking, settingsActive, open, onClose, onNew, onPick, onSettings }: Props) {
  const {query, setQuery, results, searching, searchError, retry: retrySearch} = useChatSearch(cases);
  const asideRef = useRef<HTMLElement>(null);

  useSidebarBoundary(asideRef, open, onClose);

  const currentCases = new Map(cases.map(chat => [chat.id,chat]));
  const visibleCases = query.trim() ? results.filter(chat => currentCases.has(chat.id)).map(chat => currentCases.get(chat.id)!) : cases;
  const groups = [
    {title:'Закреплённые',items:visibleCases.filter(chat => chat.pinned)},
    {title:'Недавние',items:visibleCases.filter(chat => !chat.pinned)},
  ].filter(group => group.items.length > 0);

  return (
    <>
      {open && <div className="cab-scrim" onClick={onClose} aria-hidden="true" />}
      <aside ref={asideRef} className={`cab-side ${open ? 'open' : ''} ${collapsed ? 'collapsed' : ''}`} aria-label="Дела">
        <div className="cab-side-head"><Link href="/" className="cab-brand">
          <LogoMark size={30} color="#141414" />
          <span>Цифровой судья</span>
        </Link><button type="button" className="btn btn-soft btn-icon" aria-label="Свернуть боковое меню" onClick={onClose}><Icon name="sidebar" size={18} /></button></div>
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
        {signingOut && <p className="cab-operation" role="status"><span className="spin" aria-hidden="true" />Выходим из аккаунта…</p>}
        {pinError && <p className="cab-search-status" role="alert">{pinError}</p>}
        {deleteError && <p className="cab-search-status" role="alert">{deleteError}</p>}
        {deleteNotice && <p className="cab-search-status" role="status">{deleteNotice}</p>}
        <nav className="cab-list" aria-label="Список дел" aria-busy={searching || listLoading}>
          {listLoading && !cases.length && <div className="cab-list-placeholder" role="status">Загружаем дела…<span className="cab-skeleton shimmer" aria-hidden="true" /><span className="cab-skeleton shimmer" aria-hidden="true" /></div>}
          {listError && <StateNotice error busy={listLoading} onRetry={onRetryList}>{listError}</StateNotice>}
          {!listLoading && !listError && !query.trim() && !cases.length && <p className="cab-list-placeholder" role="status">Здесь появятся ваши дела. Начните новое дело.</p>}
          {searching && <p className="cab-search-status" role="status">Ищем по названию, сообщениям и файлам…</p>}
          {searchError && <div className="cab-search-status" role="alert">{searchError}<button type="button" onClick={retrySearch}>Повторить</button></div>}
          {query.trim() && !searching && !searchError && !results.length && <p className="cab-search-status" role="status">Ничего не найдено. Попробуйте другой запрос.</p>}
          {groups.flatMap((g) => [
              <span key={`group:${g.title}`} className="cab-group-title">{g.title}</span>,
              ...g.items.map((c) => {
                const on = c.id === activeId;
                const status = on && thinking ? 'busy' : c.status;
                // layout = FLIP: pinning/unpinning slides the row between groups
                // (movement only — the row never scales, fades or unmounts).
                return (
                  <motion.div layout key={c.id} className={`cab-chat-row ${on ? 'on' : ''} ${pinningId === c.id ? 'pinning' : ''}`}
                    aria-busy={pinningId === c.id || undefined}>
                  <button type="button" className={`cab-row ${on ? 'on' : ''}`} aria-current={on ? 'page' : undefined} onClick={() => onPick(c)}>
                    <span className={`cab-dot ${status}`} aria-hidden="true" />
                    <span className="cab-row-text">
                      <span className="cab-row-title">{c.title}</span>
                      <span className="cab-row-meta">{on && thinking ? 'Идёт анализ' : c.meta}</span>
                    </span>
                  </button>
                  <ActionMenu label={`Действия чата «${c.title}»`} className="cab-chat-actions" actions={[
                    {label:c.pinned ? 'Открепить' : 'Закрепить',icon:<Icon name="pin" size={16} />,disabled:pinningId !== null,run:() => onPin(c)},
                    {label:'Удалить чат',icon:<Icon name="trash" size={16} />,danger:true,disabled:deletingId !== null || status === 'busy',run:() => onDelete(c)},
                  ]}><Icon name="dots" size={19} strokeWidth={3} /></ActionMenu>
                  </motion.div>
                );
              })
          ])}
        </nav>

        <ActionMenu placement="above" matchTriggerWidth className={`cab-row cab-profile ${settingsActive ? 'on' : ''}`} label="Аккаунт" actions={[
            {label:'Настройки аккаунта',disabled:signingOut,icon:<Icon name="gear" size={17} />,run:onSettings},
            {label:'Выйти',disabled:signingOut,icon:<Icon name="logout" size={17} />,run:onSignOut},
          ]}>
          <span className="avatar" aria-hidden="true">
            {profile?.avatar ? <img src={profile.avatar} alt="" /> : (profile?.firstName || username).slice(0, 2).toUpperCase()}
          </span>
          <span className="cab-row-text">
            <span className="cab-row-title">{[profile?.firstName, profile?.lastName].filter(Boolean).join(' ') || username}</span>
            <span className="cab-row-meta">Личный кабинет</span>
          </span>
          <Icon name="gear" size={18} color="#707070" />
        </ActionMenu>
      </aside>
    </>
  );
}
