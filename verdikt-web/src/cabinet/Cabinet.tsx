import { useCallback, useEffect, useRef, useState } from 'react';
import { api, accountApi, fileExt, mapAnalysis, type Message, type AuthUser, type Profile } from '../api/client';
import type { CaseAnalysis, CaseFile, CaseSummary } from '../api/types';
import { Icon } from '../components/Icon';
import { ChatTimeline } from './ChatTimeline';
import { DocumentPanel } from './DocumentPanel';
import { useDocumentPanel } from './useDocumentPanel';
import { Composer } from './Composer';
import { AttachScreen, NewCaseScreen } from './screens';
import { SettingsScreen } from './Settings';
import { Sidebar } from './Sidebar';
import { useChatPin } from './useChatPin';
import { useDeleteChat } from './useDeleteChat';
import { DeleteChatDialog } from './DeleteChatDialog';
import './cabinet.css';

export type CabinetView = 'new' | 'attach' | 'thinking' | 'result' | 'settings';
export interface CabinetRoute { view: CabinetView; caseId: string }

export function parseCabinetPath(path: string): CabinetRoute {
  const parts = path.split('/').filter(Boolean).slice(1);
  if (parts[0] === 'case' && parts[1]) {
    return {view: parts[2] === 'analysis' ? 'thinking' : 'result', caseId: parts[1]};
  }
  return {view: parts[0] === 'settings' ? 'settings' : parts[0] === 'attach' ? 'attach' : 'new', caseId:''};
}

interface Props { route: CabinetRoute; onNavigate: (to: string, replace?: boolean) => void; user: AuthUser; onSignOut: () => Promise<void> }

export function Cabinet({route, onNavigate, user: account, onSignOut}: Props) {
  const {view, caseId} = route;
  const documentPanel = useDocumentPanel(caseId || view);
  const [accountProfile, setAccountProfile] = useState<Profile | null>(null);
  useEffect(() => {
    let current = true;
    void accountApi.profile().then(p => { if (current) setAccountProfile(p); }).catch(() => {});
    return () => { current = false; };
  }, []);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [prompt, setPrompt] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const scroll = useRef<HTMLDivElement>(null);
  const lastStatus = messages.at(-1)?.status;
  useEffect(() => { scroll.current?.scrollTo({top:scroll.current.scrollHeight, behavior:'instant'}); }, [messages.length, lastStatus]);
  const [analysis, setAnalysis] = useState<CaseAnalysis | null>(null);
  const [error, setError] = useState('');
  const [listError, setListError] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(false);
  // Practice comparison is on by default: the shared base is open to every user.
  const [retry, setRetry] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const closeSidebar = useCallback(() => {
    setSidebarOpen(false);
    if (!window.matchMedia('(max-width: 760px)').matches) setSidebarCollapsed(true);
  }, []);
  const draftId = useRef<string | null>(null);
  const sendingRef = useRef(false);
  const operation = useRef(0);
  useEffect(() => {
    operation.current += 1;
    sendingRef.current = false;
    setSending(false);
  }, [caseId, view]);
  const listRequest = useRef(0);
  const refreshCases = useCallback(async () => {
    const request = ++listRequest.current;
    try { const next = await api.listCases(); if (request === listRequest.current) { setCases(next); setListError(''); } }
    catch (e) { setListError(e instanceof Error ? e.message : 'Не удалось загрузить список дел'); }
  }, []);
  useEffect(() => { void refreshCases(); }, [refreshCases]);
  const pin = useChatPin(refreshCases);

  useEffect(() => {
    setMessages([]); setAnalysis(null); setError('');
    if (!caseId) { setLoading(false); return; }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true);
    const poll = async () => {
      try {
        const next = await api.getMessages(caseId, controller.signal);
        if (controller.signal.aborted) return;
        setMessages(next); setLoading(false); setError('');
        const latest = [...next].reverse().find(m => m.role === 'assistant');
        setAnalysis(latest?.result ? mapAnalysis(latest.result) : null);
        if (latest?.status === 'pending' || latest?.status === 'running') {
          timer = setTimeout(poll, 1000);
        } else { void refreshCases(); }
      } catch (e) {
        if (controller.signal.aborted) return;
        setLoading(false);
        setError(e instanceof Error ? e.message : 'Не удалось загрузить анализ');
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [caseId, retry, refreshCases]);

  const assistant = [...messages].reverse().find(m => m.role === 'assistant');
  const busy = sending || assistant?.status === 'pending' || assistant?.status === 'running';
  const pendingFiles: CaseFile[] = selectedFiles.map(f => ({name:f.name, ext:fileExt(f.name), pages:0, recognition:'pending'}));
  const active = cases.find(c => c.id === caseId);
  const go = (to: string) => {
    operation.current += 1;
    sendingRef.current = false;
    setSending(false);
    setSidebarOpen(false);
    onNavigate(to);
  };
  const startNew = () => {
    draftId.current = null; setSelectedFiles([]); setPrompt(''); setError(''); go('/app');
  };
  const deletion = useDeleteChat(id => {
    listRequest.current += 1;
    setCases(current => current.filter(c => c.id !== id));
    if (draftId.current === id) draftId.current = null;
    if (caseId === id) { setMessages([]); setAnalysis(null); startNew(); }
  });
  const addFiles = (list: FileList | null) => {
    if (busy) return;
    if (list) setSelectedFiles(prev => [...prev, ...Array.from(list)]);
    if (!caseId) go('/app/attach');
  };
  const send = async () => {
    if (sendingRef.current || busy || (!prompt.trim() && !selectedFiles.length)) return;
    const token = ++operation.current;
    const initialPath = window.location.pathname;
    const isCurrent = () => operation.current === token && window.location.pathname === initialPath;
    sendingRef.current = true; setSending(true); setError('');
    try {
      const id = caseId || draftId.current || String((await api.createCase()).id);
      if (!caseId && isCurrent()) draftId.current = id;
      await api.sendCase(id, prompt, selectedFiles, true);
      void refreshCases();
      if (!isCurrent()) return;
      setSelectedFiles([]); setPrompt(''); setRetry(n => n + 1);
      go(`/app/case/${id}/analysis`);
      void refreshCases();
    } catch (e) { if (isCurrent()) setError(e instanceof Error ? e.message : 'Не удалось отправить запрос'); }
    finally { if (isCurrent()) { sendingRef.current = false; setSending(false); } }
  };

  return (
    <div className={`cab ${documentPanel.state ? 'cab-with-document' : ''} ${sidebarCollapsed ? 'cab-sidebar-collapsed' : ''}`}>
      {deletion.pendingChat && <DeleteChatDialog chat={deletion.pendingChat} busy={deletion.deletingId !== null}
        error={deletion.deleteError} onCancel={deletion.cancel} onConfirm={() => { void deletion.confirm(); }} />}
      <Sidebar collapsed={sidebarCollapsed} pinningId={pin.pendingId} pinError={pin.error}
        onPin={chat => { void pin.toggle(chat); }}
        onSignOut={() => { void onSignOut().catch(() => setError('Не удалось выйти. Попробуйте ещё раз.')); }}
        deletingId={deletion.deletingId} deleteError="" deleteNotice={deletion.deleteNotice}
        onDelete={deletion.remove} cases={cases} activeId={caseId || null} thinking={busy} settingsActive={view === 'settings'}
        open={sidebarOpen} onClose={closeSidebar} onNew={startNew}
        onPick={c => { setSelectedFiles([]); setPrompt(''); go(`/app/case/${c.id}/result`); }}
        onSettings={() => go('/app/settings')} username={account.username} profile={accountProfile} />
      <main className="cab-main">
        <header className="cab-header">
          <div className="cab-header-title">
            <button type="button" className="btn btn-soft btn-icon cab-menu" aria-label="Открыть боковое меню"
              aria-expanded={sidebarOpen} onClick={() => { setSidebarCollapsed(false); setSidebarOpen(true); }}><Icon name="menu" size={18} /></button>
            <span className="cab-title">{view === 'settings' ? 'Профиль' : active?.title || (caseId ? `Дело ${caseId}` : 'Новое дело')}</span>
            {analysis && !busy && <span className="badge">Анализ готов</span>}
          </div>
        </header>
        <div ref={scroll} className="cab-scroll">
          {listError && <div className="warn-box" role="alert">{listError}<button type="button" onClick={() => void refreshCases()}>Повторить</button></div>}
          {error && <div className="warn-box" role="alert">{error}<button type="button" onClick={() => setRetry(n => n + 1)}>Обновить</button></div>}
          {loading && <p role="status" aria-busy="true">Загружаем дело…</p>}
          {view === 'settings' ? <SettingsScreen onProfileSaved={setAccountProfile} user={account} onCancel={() => go('/app')} onSignOut={onSignOut} onDeleted={async () => { draftId.current = null; setSelectedFiles([]); setPrompt(''); await refreshCases(); }} /> : caseId ? (
            <>
              {messages.length > 0 ? <ChatTimeline chatId={caseId} messages={messages} onOpen={attachment => documentPanel.open({name:attachment.filename,chatId:caseId,attachmentId:attachment.id})}
                onOpenVerdict={verdict => { if (verdict.verdict_id != null) documentPanel.open({name:`Приговор · ${verdict.court}.txt`, verdictId:verdict.verdict_id}); }} /> :
                !loading && !error && <p>Задайте вопрос или прикрепите материалы дела.</p>}
              {selectedFiles.length > 0 && <AttachScreen files={pendingFiles} onOpen={index => { const file = selectedFiles[index]; if (file) documentPanel.open({name:file.name,file}); }} onRemove={name => setSelectedFiles(p => p.filter(f => f.name !== name))} />}
            </>
          ) : view === 'attach' || selectedFiles.length ? <AttachScreen files={pendingFiles} onOpen={index => { const file = selectedFiles[index]; if (file) documentPanel.open({name:file.name,file}); }} onRemove={name => setSelectedFiles(p => p.filter(f => f.name !== name))} /> : <NewCaseScreen onFiles={addFiles} />}
        </div>
        {view !== 'settings' && <>
          <Composer mode={busy ? 'thinking' : selectedFiles.length ? 'attach' : 'idle'} files={pendingFiles}
            value={prompt} onChange={setPrompt} onFiles={addFiles} onSend={() => void send()}
            onStop={() => go('/app')} />
        </>}
      </main>
      {documentPanel.state && <DocumentPanel {...documentPanel.state} onClose={documentPanel.close} onRetry={documentPanel.retry} />}
    </div>
  );
}
