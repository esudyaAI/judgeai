import { useEffect, useState } from 'react';

export function useElapsedSeconds(startedAt?: string) {
  const [mountedAt] = useState(() => Date.now());
  const parsed = startedAt ? Date.parse(startedAt) : NaN;
  const start = Number.isFinite(parsed) ? parsed : mountedAt;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return Math.max(0, Math.floor((now - start) / 1000));
}
