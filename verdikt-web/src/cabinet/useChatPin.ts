import { useRef, useState } from 'react';
import { api } from '../api/client';
import type { CaseSummary } from '../api/types';

export function useChatPin(onChanged: () => Promise<void>) {
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const locked = useRef(false);
  const callback = useRef(onChanged);
  callback.current = onChanged;
  async function toggle(chat: CaseSummary) {
    if (locked.current) return;
    locked.current = true; setPendingId(chat.id); setError('');
    try { await api.pinCase(chat.id,!chat.pinned); await callback.current(); }
    catch (error) { setError(error instanceof Error ? error.message : 'Не удалось закрепить чат'); }
    finally { locked.current = false; setPendingId(null); }
  }
  return {pendingId,error,toggle};
}
