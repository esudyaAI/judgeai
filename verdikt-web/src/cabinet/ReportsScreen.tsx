import {useEffect, useRef, useState} from 'react';
import {mapAnalysis, reportsApi, type ReportDetail, type ReportSummary} from '../api/client';
import {Result} from './screens';

export function ReportDownload({report}: {report: ReportSummary}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const lock = useRef(false);
  const download = async () => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try { await reportsApi.download(report); }
    catch (e) { setError(e instanceof Error ? e.message : 'Не удалось скачать отчёт'); }
    finally { lock.current = false; setBusy(false); }
  };
  return <div><button type="button" className="btn btn-soft" disabled={busy} onClick={() => void download()}>{busy ? 'Загружаем…' : 'Скачать DOCX'}</button>{error && <p role="alert">{error}</p>}</div>;
}

export function CreateReportButton({chatId, messageId}: {chatId: string; messageId: number}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState<ReportSummary | null>(null);
  const lock = useRef(false);
  const create = async () => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try {
      const report = await reportsApi.create(chatId, messageId);
      setSaved(report);
      await reportsApi.download(report);
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось сохранить отчёт'); }
    finally { lock.current = false; setBusy(false); }
  };
  return <div className="report-actions">
    <button type="button" className="btn btn-soft" disabled={busy} onClick={() => void create()}>{busy ? 'Готовим отчёт…' : 'Скачать DOCX'}</button>
    {saved && <a href={`/app/reports/${saved.id}`}>Отчёт · версия {saved.version}</a>}
    {error && <p role="alert">{error}</p>}
  </div>;
}

export function ReportsScreen({reportId, onNavigate}: {reportId?: string; onNavigate: (path: string) => void}) {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => { setOffset(0); }, [reportId]);
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true); setError(''); setDetail(null); setReports([]);
    void (async () => {
      try {
        const result = reportId ? await reportsApi.get(reportId, controller.signal) : null;
        const rows = await reportsApi.list(offset, controller.signal, result?.chat_id);
        if (!controller.signal.aborted) { setDetail(result); setReports(rows); }
      } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Не удалось загрузить отчёты'); }
      finally { if (!controller.signal.aborted) setBusy(false); }
    })();
    return () => controller.abort();
  }, [reportId, offset, retry]);
  return <section className="thread reports-screen" aria-label="Сохранённые отчёты">
    <h1>Отчёты</h1>
    {reportId && <button className="btn btn-soft" type="button" onClick={() => onNavigate('/app/reports')}>Все отчёты</button>}
    {busy && <p role="status">Загружаем отчёты…</p>}
    {error && <div role="alert">{error}<button type="button" onClick={() => setRetry(n => n + 1)}>Повторить</button></div>}
    {!busy && !error && <>
      {detail && <>
        <h2>{detail.snapshot.chat_title || `Дело ${detail.chat_id}`} · версия {detail.version}</h2>
        <p>Сохранённый результат от {new Date(detail.created_at).toLocaleString('ru-RU')}. Расчёты не обновляются.</p>
        <p>{detail.snapshot.human_review?.status === 'not_reviewed' ? 'Не проверено человеком' : detail.snapshot.human_review?.status === 'partially_reviewed' ? 'Часть фактов проверена пользователем; правовая приёмка не выполнена' : 'Состояние проверки человеком неизвестно'}</p>
        <ReportDownload report={detail} />
        {detail.snapshot.limitations.map((text, index) => <p className="warn-box" key={index}>{text}</p>)}
        <Result a={mapAnalysis(detail.snapshot.analysis)} />
        <h2>История версий этого дела</h2>
      </>}
      {!reports.length && <p>Сохранённых отчётов пока нет. После анализа нажмите «Скачать DOCX».</p>}
      <ul className="report-list">{reports.map(report => <li key={report.id}>
        <button type="button" className="btn btn-soft" onClick={() => onNavigate(`/app/reports/${report.id}`)}>Дело {report.chat_id} · версия {report.version}</button>
        <span>{new Date(report.created_at).toLocaleString('ru-RU')}</span>
        <ReportDownload report={report} />
      </li>)}</ul>
      <div className="report-actions">
        {offset > 0 && <button type="button" className="btn btn-soft" onClick={() => setOffset(n => Math.max(0, n - 50))}>Предыдущие</button>}
        {reports.length === 50 && <button type="button" className="btn btn-soft" onClick={() => setOffset(n => n + 50)}>Следующие</button>}
      </div>
    </>}
  </section>;
}
