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

/** 30 → «30 сек», 119 → «1 мин 59 сек», 120 → «2 мин». */
export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  if (total < 60) return `${total} сек`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${minutes} мин ${rest} сек` : `${minutes} мин`;
}
