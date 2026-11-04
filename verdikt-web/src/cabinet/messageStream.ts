import type { Message } from '../api/client';

/** Owns the connection; a failed transport falls back to REST for this subscription. */
export function subscribeMessages(
  caseId: string,
  messages: (value: Message[]) => void,
  done: () => void,
  fallback: () => void,
): (() => void) | null {
  if (typeof EventSource === 'undefined') return null;
  let source: EventSource;
  try { source = new EventSource(`/api/chats/${encodeURIComponent(caseId)}/messages/stream`); }
  catch { return null; }
  let closed = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  const close = () => { closed = true; clearTimeout(reconnectTimer); source.close(); };
  const fail = () => { if (!closed) { close(); fallback(); } };
  source.addEventListener('messages', event => {
    if (closed) return;
    clearTimeout(reconnectTimer); reconnectTimer = undefined;
    try {
      const value: unknown = JSON.parse((event as MessageEvent).data);
      if (!Array.isArray(value)) { fail(); return; }
      messages(value as Message[]);
    } catch { fail(); }
  });
  source.addEventListener('access_revoked', fail);
  source.addEventListener('done', () => { if (!closed) { close(); done(); } });
  reconnectTimer = setTimeout(fail, 10000);
  source.onopen = () => { clearTimeout(reconnectTimer); reconnectTimer = undefined; };
  source.onerror = () => {
    if (closed) return;
    if (source.readyState === 0) {
      reconnectTimer ??= setTimeout(fail, 10000);
    } else fail();
  };
  return close;
}
