import type { CaseAnalysis, CaseFile, CaseSummary, LegalCheck, PrecedentSource } from './types';

type WireScale = {
  sanction_max_months: number; limit_months: number | null; limit_norm: string | null;
  practice_months: [number, number] | null; avg_similar_months: number | null;
  recommended_months: number | null; within_sanction: boolean | null; extra_notes: string[];
};
export type WireAnalysis = Omit<CaseAnalysis, 'scale' | 'legalChecks' | 'precedentSource' | 'practiceEpisodes'> & {
  schema_version: number; scale: WireScale | null; legal_checks?: LegalCheck[];
  precedent_source?: PrecedentSource;
  practice_episodes?: import('./types').PracticeComparison[];
};
export interface Message {
  id: number; role: string; content: string | null;
  status: 'pending' | 'running' | 'completed' | 'failed'; stage: string | null;
  error: string | null; result: WireAnalysis | null;
  attachments: { id: number; filename: string; page_count: number | null;
    extraction_status: CaseFile['recognition'] }[];
}
interface Chat { id: number; title: string | null; status: CaseSummary['status']; updated_at: string }

export interface AuthUser { id: number; username: string; is_admin: boolean; csrf_token: string }
let csrfToken = '';
export class AuthenticationError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (csrfToken && init?.method && !['GET', 'HEAD'].includes(init.method)) {
    headers.set('X-CSRF-Token', csrfToken);
  }
  const response = await fetch(`/api${path}`, {...init, headers, credentials: 'same-origin'});
  if (response.status === 401) {
    csrfToken = '';
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('judgeai:unauthorized'));
    const body = await response.json().catch(() => null);
    throw new AuthenticationError(typeof body?.detail === 'string' ? body.detail : 'Требуется вход');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Ошибка запроса (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function mapAnalysis(a: WireAnalysis): CaseAnalysis {
  const s = a.scale;
  return { ...a, qualification: a.qualification ?? null, draft: a.draft ?? null,
    warnings: a.warnings ?? [], legalChecks: a.legal_checks ?? [],
    precedentSource: a.precedent_source ?? null, precedents: a.precedents ?? [],
    practice: a.practice ?? null,
    practiceEpisodes: a.practice_episodes ?? [],
    scale: s ? {sanctionMaxMonths: s.sanction_max_months, limitMonths: s.limit_months,
      limitNorm: s.limit_norm, practiceMonths: s.practice_months,
      avgSimilarMonths: s.avg_similar_months, recommendedMonths: s.recommended_months,
      withinSanction: s.within_sanction, extraNotes: s.extra_notes ?? []} : null };
}

export function fileExt(name: string): CaseFile['ext'] {
  const ext = name.split('.').pop()?.toLowerCase();
  return ext === 'pdf' ? 'PDF' : ext === 'docx' ? 'DOC' : ext === 'txt' || ext === 'md' ? 'TXT' : 'JPG';
}

export const api = {
  async listCases(query = '', signal?: AbortSignal): Promise<CaseSummary[]> {
    const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : '';
    const chats = await request<Chat[]>(`/chats${suffix}`, {signal});
    const labels = {draft: 'Черновик', busy: 'Идёт анализ', ready: 'Анализ готов', failed: 'Ошибка анализа'};
    return chats.map(c => ({id: String(c.id), title: c.title || 'Дело без названия',
      group: 'Ранее', status: c.status, meta: labels[c.status]}));
  },
  deleteCase(id: string): Promise<{deleted: number; files_pending: number}> {
    return request(`/chats/${encodeURIComponent(id)}`, {method: 'DELETE'});
  },
  createCase(): Promise<Chat> {
    return request('/chats', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:null})});
  },
  getMessages(id: string, signal?: AbortSignal): Promise<Message[]> {
    return request(`/chats/${encodeURIComponent(id)}/messages`, {signal});
  },
  sendCase(id: string, content: string, files: File[], useKnowledge = false): Promise<{assistant_message: Message}> {
    const body = new FormData();
    body.set('content', content);
    body.set('use_knowledge_base', String(useKnowledge));
    for (const file of files) body.append('files', file);
    return request(`/chats/${encodeURIComponent(id)}/messages`, {method:'POST', body});
  },
};


export const auth = {
  async me(): Promise<AuthUser> {
    const user = await request<AuthUser>('/auth/me');
    csrfToken = user.csrf_token;
    return user;
  },
  async login(username: string, password: string): Promise<AuthUser> {
    csrfToken = '';
    try {
      const user = await request<AuthUser>('/auth/login', {method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Requested-With': 'JudgeAI'},
        body: JSON.stringify({username, password})});
      csrfToken = user.csrf_token;
      return user;
    } catch (error) {
      if (error instanceof AuthenticationError) throw new Error('Неверное имя пользователя или пароль');
      throw error;
    }
  },
  /** Open self-registration of an ordinary account; signs the new user in. */
  async register(username: string, password: string): Promise<AuthUser> {
    csrfToken = '';
    const user = await request<AuthUser>('/auth/register', {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Requested-With': 'JudgeAI'},
      body: JSON.stringify({username, password})});
    csrfToken = user.csrf_token;
    return user;
  },
  async logout(): Promise<void> {
    await request('/auth/logout', {method: 'POST'});
    csrfToken = '';
  },
};

export interface Profile {
  firstName: string; lastName: string; email: string; position: string;
  org: string; region: string; avatar: string;
}
export interface AccountSession { id: string; current: boolean; created_at: string; expires_at: string }
export const accountApi = {
  profile: () => request<Profile>('/account/profile'),
  saveProfile: (profile: Profile) => request<Profile>('/account/profile', {
    method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(profile),
  }),
  sessions: () => request<AccountSession[]>('/account/sessions'),
  revoke: (id: string) => request(`/account/sessions/${encodeURIComponent(id)}`, {method: 'DELETE'}),
  changePassword: (current: string, next: string) => request('/account/password', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({current_password: current, new_password: next}),
  }),
  exportData: () => request<unknown>('/account/export'),
  deleteCases: (password: string, confirmation: string) => request<{deleted: number; files_pending: number}>('/account/delete-cases', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({password, confirmation}),
  }),
};
