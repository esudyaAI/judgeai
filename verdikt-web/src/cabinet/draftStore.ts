/**
 * Unsent new-case draft (composer text + attached files) persisted locally, so
 * leaving to another chat, reloading the page or closing the tab does not lose
 * work in progress. Files are too big for localStorage — they live in
 * IndexedDB as structured-cloned Blobs and are rebuilt as File on restore.
 *
 * The storage interface is injectable so the pacing, validation and clearing
 * rules are unit-tested in node without a DOM; the IDB adapter stays thin.
 */

export interface NewCaseDraft {
  prompt: string;
  files: File[];
}

export interface DraftStorage {
  load(): Promise<NewCaseDraft | null>;
  save(draft: NewCaseDraft): Promise<void>;
  clear(): Promise<void>;
}

/** Every storage failure (private mode, quota, blocked IDB) degrades to «no draft». */
export function noopDraftStorage(): DraftStorage {
  return { load: () => Promise.resolve(null), save: () => Promise.resolve(), clear: () => Promise.resolve() };
}

/** In-memory storage for tests and for browsers without IndexedDB. */
export function memoryDraftStorage(): DraftStorage {
  let record: NewCaseDraft | null = null;
  return {
    load: () => Promise.resolve(record),
    save: (draft) => { record = draft; return Promise.resolve(); },
    clear: () => { record = null; return Promise.resolve(); },
  };
}

const DB_NAME = 'verdikt-drafts';
const STORE = 'drafts';
const KEY = 'new-case';

interface StoredFile { name: string; type: string; lastModified: number; data: Blob }
interface DraftRecordV1 { v: 1; prompt: string; files: StoredFile[] }

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => { request.result.createObjectStore(STORE); };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function run<T>(db: IDBDatabase, mode: IDBTransactionMode, op: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const request = op(tx.objectStore(STORE));
    request.onsuccess = () => resolve(request.result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

/** A stored record is trusted only when every field validates; anything else is dropped. */
export function parseStoredDraft(raw: unknown): NewCaseDraft | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const record = raw as Partial<DraftRecordV1>;
  if (record.v !== 1 || typeof record.prompt !== 'string' || !Array.isArray(record.files)) return null;
  const files: File[] = [];
  for (const item of record.files) {
    if (typeof item !== 'object' || item === null) return null;
    const { name, type, lastModified, data } = item as Partial<StoredFile>;
    if (typeof name !== 'string' || !(data instanceof Blob)) return null;
    files.push(new File([data], name, {
      type: typeof type === 'string' ? type : '',
      lastModified: typeof lastModified === 'number' ? lastModified : Date.now(),
    }));
  }
  return { prompt: record.prompt, files };
}

export function serializeDraft(draft: NewCaseDraft): DraftRecordV1 {
  return {
    v: 1,
    prompt: draft.prompt,
    files: draft.files.map((f) => ({ name: f.name, type: f.type, lastModified: f.lastModified, data: f })),
  };
}

export function idbDraftStorage(): DraftStorage {
  if (typeof indexedDB === 'undefined') return noopDraftStorage();
  const withDb = async <T>(op: (db: IDBDatabase) => Promise<T>): Promise<T> => {
    const db = await openDb();
    try { return await op(db); } finally { db.close(); }
  };
  return {
    load: () => withDb((db) => run(db, 'readonly', (store) => store.get(KEY)))
      .then((raw) => parseStoredDraft(raw))
      .catch(() => null),
    save: (draft) => withDb((db) => run(db, 'readwrite', (store) => store.put(serializeDraft(draft), KEY)))
      .then(() => undefined).catch(() => undefined),
    clear: () => withDb((db) => run(db, 'readwrite', (store) => store.delete(KEY)))
      .then(() => undefined).catch(() => undefined),
  };
}

export interface DraftSaver {
  /** Debounce a write; only the latest draft is ever persisted. */
  schedule(draft: NewCaseDraft): void;
  /** Persist the pending draft right now (pagehide, sign-out, unmount). */
  flush(): void;
  /** Cancel any pending write and drop the stored draft (successful send, sign-out). */
  clear(): void;
}

export function createDraftSaver(storage: DraftStorage, delayMs = 250): DraftSaver {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pending: NewCaseDraft | null = null;
  const write = (draft: NewCaseDraft) =>
    draft.prompt.trim() || draft.files.length ? storage.save(draft) : storage.clear();
  return {
    schedule(draft) {
      pending = draft;
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        const draftToWrite = pending;
        pending = null;
        if (draftToWrite) void write(draftToWrite);
      }, delayMs);
    },
    flush() {
      if (timer) { clearTimeout(timer); timer = null; }
      const draftToWrite = pending;
      pending = null;
      if (draftToWrite) void write(draftToWrite);
    },
    clear() {
      if (timer) { clearTimeout(timer); timer = null; }
      pending = null;
      void storage.clear();
    },
  };
}
