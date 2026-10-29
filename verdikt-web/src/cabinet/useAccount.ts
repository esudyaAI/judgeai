import { useEffect, useRef, useState } from 'react';
import { accountApi, type Profile, type AccountSession } from '../api/client';

export const EMPTY_PROFILE: Profile = {firstName:'', lastName:'', email:'', position:'', org:'', region:'', avatar:''};

export function useAccount() {
  const [profile, setProfile] = useState<Profile>(EMPTY_PROFILE);
  const [sessions, setSessions] = useState<AccountSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pendingAction, setPendingAction] = useState('');
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [retry, setRetry] = useState(0);
  const lock = useRef(false);
  useEffect(() => {
    let current = true;
    setLoading(true); setLoaded(false); setError('');
    void Promise.all([accountApi.profile(), accountApi.sessions()]).then(([p, s]) => {
      if (current) { setProfile(p); setSessions(s); setLoaded(true); }
    }).catch(e => { if (current) setError(e instanceof Error ? e.message : 'Не удалось загрузить профиль'); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [retry]);
  async function run(action: () => Promise<void>, key = 'action') {
    if (lock.current) return;
    lock.current = true; setBusy(true); setPendingAction(key); setError(''); setStatus('');
    try { await action(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Не удалось выполнить действие'); }
    finally { lock.current = false; setBusy(false); setPendingAction(''); }
  }
  return {profile, setProfile, sessions, setSessions, loading, loaded, busy, pendingAction, error, setError, status, setStatus,
    run, reload: () => setRetry(n => n + 1)};
}

export {prepareAvatar as readAvatar} from './avatarImage';

export function downloadAccountData(data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a');
  link.href = url; link.download = 'judgeai-data.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
