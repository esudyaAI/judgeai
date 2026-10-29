import { useRef, useState, type ReactNode } from 'react';
import { accountApi, type AuthUser, type Profile } from '../api/client';
import { Link } from '../router';
import { readAvatar, useAccount } from './useAccount';
import {BusyButton, StateNotice} from '../components/UiState';
import {canChangePassword} from '../auth/formValidity';
import {AnimatePresence} from 'motion/react';
import {PresenceSurface} from '../components/PresenceSurface';

type Tab = 'profile' | 'security' | 'data';
const TABS: [Tab, string][] = [['profile', 'Профиль'], ['security', 'Безопасность'], ['data', 'Данные']];
const FIELDS: [keyof Omit<Profile, 'avatar'>, string, string][] = [
  ['firstName', 'Имя', 'Имя'], ['lastName', 'Фамилия', 'Фамилия'], ['email', 'Электронная почта', 'name@example.ru'],
  ['position', 'Должность', 'Например, помощник судьи'], ['org', 'Суд или организация', 'Название'], ['region', 'Регион', 'Регион'],
];
const LIMITS = {firstName:100, lastName:100, email:254, position:200, org:200, region:100};
function Row({title, hint, children}: {title: string; hint: string; children: ReactNode}) {
  return <div className="set-row"><div><div className="set-title">{title}</div><div className="muted-14">{hint}</div></div>{children}</div>;
}

export function SettingsScreen({user, onCancel, onDeleted, onSignOut, onProfileSaved}: {
  onProfileSaved: (profile: Profile) => void;
  user: AuthUser; onCancel: () => void; onDeleted: () => Promise<void>; onSignOut: () => Promise<void>;
}) {
  const state = useAccount();
  const {profile, setProfile, sessions, loading, busy, error, status, run, setStatus} = state;
  const [tab, setTab] = useState<Tab>('profile');
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const photo = useRef<HTMLInputElement>(null);

  return <div className="fade-in settings">
    <h1 className="screen-h2">Настройки аккаунта</h1>
    <div role="tablist" aria-label="Разделы настроек" className="seg">
      {TABS.map(([id, label]) => <button key={id} type="button" role="tab" id={`tab-${id}`} aria-controls={`panel-${id}`} aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} disabled={busy}
        onKeyDown={event => {
          const index = TABS.findIndex(([value]) => value === id);
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? TABS.length-1 : event.key === 'ArrowRight' ? (index+1)%TABS.length : event.key === 'ArrowLeft' ? (index+TABS.length-1)%TABS.length : -1;
          if (next < 0) return;
          event.preventDefault(); setTab(TABS[next][0]); state.setError(''); setStatus('');
          document.getElementById(`tab-${TABS[next][0]}`)?.focus();
        }}
        onClick={() => { setTab(id); state.setError(''); setStatus(''); }}>{label}</button>)}
    </div>
    {loading && <StateNotice busy>Загружаем настройки…</StateNotice>}
    {error && <div className="warn-box" role="alert">{error}<button type="button" disabled={busy} onClick={state.reload}>Загрузить заново</button></div>}
    {status && <p role="status">{status}</p>}
    <AnimatePresence mode="wait" initial={false}>{!loading && state.loaded && <PresenceSurface role="tabpanel" tabIndex={0} id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} key={tab}>
      {tab === 'profile' && <form className="set-profile" onSubmit={e => {
        e.preventDefault(); void run(async () => { const saved = await accountApi.saveProfile(profile); setProfile(saved); onProfileSaved(saved); setStatus('Профиль сохранён'); }, 'profile');
      }}>
        <div className="set-avatar-row">
          <span className="avatar avatar-lg" aria-hidden="true">{profile.avatar ? <img src={profile.avatar} alt="" /> : (profile.firstName || user.username).slice(0, 2).toUpperCase()}</span>
          <input ref={photo} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={e => {
            const file = e.target.files?.[0]; e.target.value = '';
            if (file) void run(async () => { const avatar = await readAvatar(file); setProfile(p => ({...p, avatar})); setStatus('Фото выбрано. Нажмите «Сохранить профиль».'); }, 'avatar');
          }} />
          <BusyButton type="button" className="btn btn-soft btn-sm" disabled={busy} pending={state.pendingAction === 'avatar'} pendingLabel="Читаем фото…" onClick={() => photo.current?.click()}>Изменить фото</BusyButton>
          {profile.avatar && <button type="button" className="btn btn-line btn-sm" disabled={busy} onClick={() => { setProfile(p => ({...p, avatar:''})); setStatus('Фото убрано. Нажмите «Сохранить профиль».'); }}>Убрать фото</button>}
        </div>
        <p className="muted-14">PNG, JPEG или WebP, до 10 МБ. Фото уменьшим автоматически.</p>
        <div className="set-fields">{FIELDS.map(([name, label, placeholder]) => <label key={name} className="set-field"><span>{label}</span>
          <input type={name === 'email' ? 'email' : 'text'} name={name} maxLength={LIMITS[name]} placeholder={placeholder} value={profile[name]} disabled={busy}
            onChange={e => { setProfile(p => ({...p, [name]: e.target.value})); setStatus(''); }} />
        </label>)}</div>
        <div className="set-actions"><BusyButton type="submit" className="btn btn-ink btn-md" disabled={busy} pending={state.pendingAction === 'profile'} pendingLabel="Сохраняем…">Сохранить профиль</BusyButton>
          <button type="button" className="btn btn-soft btn-md" disabled={busy} onClick={onCancel}>Отмена</button></div>
      </form>}
      {tab === 'security' && <div className="set-list">
        <form className="set-profile" onSubmit={e => {
          e.preventDefault();
          if (!canChangePassword(oldPassword,newPassword,repeatPassword)) { state.setError('Новые пароли не совпадают'); return; }
          void run(async () => { await accountApi.changePassword(oldPassword, newPassword);
            setOldPassword(''); setNewPassword(''); setRepeatPassword('');
            state.setSessions(await accountApi.sessions()); setStatus('Пароль изменён. Остальные сеансы завершены.'); }, 'password');
        }}>
          <h2 className="set-title">Изменить пароль</h2>
          <input type="text" autoComplete="username" value={user.username} readOnly hidden />
          <p className="muted-14">Новый пароль — не меньше 12 символов. Повторите его в обоих полях.</p>
          <div className="set-fields">
            <label className="set-field"><span>Текущий пароль</span><input type="password" autoComplete="current-password" required maxLength={1024} value={oldPassword} disabled={busy} onChange={e => setOldPassword(e.target.value)} /></label>
            <label className="set-field"><span>Новый пароль</span><input type="password" autoComplete="new-password" required minLength={12} maxLength={1024} value={newPassword} disabled={busy} onChange={e => setNewPassword(e.target.value)} /></label>
            <label className="set-field"><span>Повторите новый пароль</span><input type="password" autoComplete="new-password" required minLength={12} maxLength={1024} value={repeatPassword} disabled={busy} onChange={e => setRepeatPassword(e.target.value)} /></label>
          </div>
          {repeatPassword && newPassword !== repeatPassword && <p className="auth-error" role="status">Новые пароли не совпадают.</p>}
          <div className="set-actions"><BusyButton type="submit" className="btn btn-ink btn-md" pending={state.pendingAction === 'password'} pendingLabel="Изменяем пароль…" disabled={busy || !canChangePassword(oldPassword,newPassword,repeatPassword)}>Изменить пароль</BusyButton></div>
        </form>
        <div className="set-sessions"><h2 className="set-title">Активные сеансы</h2>
          <p className="muted-14">Открытые входы в аккаунт. Названия устройств и геолокация не собираются.</p>
          {!sessions.length && <StateNotice>Нет доступных сеансов. Обновите настройки, чтобы проверить список.</StateNotice>}
          {sessions.map(s => <div key={s.id} className="session"><div className="session-details"><strong>{s.current ? 'Этот сеанс' : 'Другой сеанс'}</strong>
            <span>Вход: {new Date(s.created_at).toLocaleString('ru-RU')}</span><span>Действует до: {new Date(s.expires_at).toLocaleString('ru-RU')}</span></div>
            <BusyButton type="button" className="btn btn-line btn-sm" disabled={busy} pending={state.pendingAction === `session:${s.id}`} pendingLabel={s.current ? 'Выходим…' : 'Завершаем…'} onClick={() => void run(async () => {
              if (s.current) await onSignOut(); else { await accountApi.revoke(s.id); state.setSessions(await accountApi.sessions()); setStatus('Сеанс завершён'); }
            }, `session:${s.id}`)}>{s.current ? 'Выйти' : 'Завершить'}</BusyButton>
          </div>)}
        </div>
      </div>}
      {tab === 'data' && <div className="set-list">
        <Row title="Обработка данных" hint="Узнайте, как разделены личные дела и общая база практики."><Link href="/privacy">Конфиденциальность</Link></Row>
        <div className="danger-box"><div><div className="set-title">Удалить все мои дела</div><p className="muted-14">Запросы, результаты и вложения будут удалены. Аккаунт и документы, отдельно сохранённые в базе практики, сохранятся.</p></div>
          {!confirming && <button type="button" className="btn btn-danger btn-sm" disabled={busy} onClick={() => setConfirming(true)}>Удалить дела</button>}
          {confirming && <form className="set-delete-confirm" onSubmit={e => {
            e.preventDefault(); void run(async () => {
              const result = await accountApi.deleteCases(deletePassword, confirmation);
              setDeletePassword(''); setConfirmation(''); setConfirming(false); await onDeleted();
              setStatus(`Удалено дел: ${result.deleted}.${result.files_pending ? ' Часть исходных файлов требует очистки оператором.' : ''}`);
            }, 'delete');
          }}>
            <p>Удаление необратимо. Сначала скачайте данные, если они вам нужны. Во время анализа удаление недоступно.</p>
            <label className="set-field"><span>Введите УДАЛИТЬ</span><input value={confirmation} required pattern="УДАЛИТЬ" disabled={busy} onChange={e => setConfirmation(e.target.value)} /></label>
            <label className="set-field"><span>Пароль аккаунта</span><input type="password" autoComplete="current-password" required maxLength={1024} value={deletePassword} disabled={busy} onChange={e => setDeletePassword(e.target.value)} /></label>
            <div className="set-actions"><BusyButton type="submit" className="btn btn-danger btn-sm" pending={state.pendingAction === 'delete'} pendingLabel="Удаляем дела…" disabled={busy || confirmation !== 'УДАЛИТЬ' || !deletePassword}>Удалить безвозвратно</BusyButton>
              <button type="button" className="btn btn-soft btn-sm" disabled={busy} onClick={() => { setConfirming(false); setConfirmation(''); setDeletePassword(''); }}>Отмена</button></div>
          </form>}
        </div>
      </div>}
    </PresenceSurface>}</AnimatePresence>
  </div>;
}
