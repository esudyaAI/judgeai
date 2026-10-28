import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { CaseSummary } from '../api/types';

export function useChatSearch(cases: CaseSummary[]) {
  const [query, setQuery] = useState('');
  const previousQuery = useRef('');
  const [results, setResults] = useState<CaseSummary[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [searchRetry, setSearchRetry] = useState(0);
  useEffect(() => {
    if (!query.trim()) { previousQuery.current = ''; setResults([]); setSearching(false); setSearchError(''); return; }
    const controller = new AbortController();
    setSearching(true); setSearchError('');
    if (previousQuery.current !== query) setResults([]);
    previousQuery.current = query;
    const timer = setTimeout(() => {
      void api.listCases(query, controller.signal).then(next => {
        if (!controller.signal.aborted) setResults(next);
      }).catch(error => {
        if (!controller.signal.aborted) setSearchError(error instanceof Error ? error.message : 'Не удалось выполнить поиск');
      }).finally(() => { if (!controller.signal.aborted) setSearching(false); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, cases, searchRetry]);
  return {query, setQuery, results, searching, searchError, retry: () => setSearchRetry(n => n + 1)};
}
