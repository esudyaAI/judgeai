import { memo, useEffect, useRef, useState, type DragEvent } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import type { CaseAnalysis, CaseFile, PracticeComparison, SimilarVerdict } from '../api/types';
import { FileChip, FileTile } from '../components/FileTile';
import { Icon, IconTile, type IconName } from '../components/Icon';
import { LogoMark } from '../components/Logo';
import { SentenceScale } from '../components/SentenceScale';
import { plural } from '../lib/format';
import { ACCEPT, filesFromClipboard } from '../lib/files';
import { fileReadingLabel, fileReadingWarning } from './fileReadingPresentation';
import {Pressable} from '../components/UiState';
import { formatElapsed, useElapsedSeconds } from './useElapsedSeconds';
import { legalCheckSourceUrl, legalCheckStatusLabel } from './legalCheckPresentation';
import { practiceSummary, precedentSourceNote, shareLabel } from './practicePresentation';

/** Clicking a card fills the composer with the prompt (it does not pick a "mode"). */
const SUGGESTIONS: { title: string; sub: string; bg: string; icon: IconName; prompt: string }[] = [
  {
    title: 'Подготовить проект приговора',
    sub: 'Квалификация, наказание и текст',
    bg: '#0066ff',
    icon: 'doc',
    prompt: 'Подготовь проект приговора по представленным материалам дела: определи квалификацию, предложи наказание и составь текст приговора.',
  },
  {
    title: 'Проверить квалификацию',
    sub: 'Статья, часть и спорные признаки',
    bg: '#141414',
    icon: 'scales',
    prompt: 'Проверь квалификацию по материалам дела: статья, часть и спорные признаки состава.',
  },
  {
    title: 'Найти схожие приговоры',
    sub: 'Практика по той же статье',
    bg: '#e5480f',
    icon: 'cmp',
    prompt: 'Найди схожие приговоры по той же статье и сравни наказание с судебной практикой.',
  },
  {
    title: 'Оценить позицию защиты',
    sub: 'Смягчающие обстоятельства и риски',
    bg: '#0f8a52',
    icon: 'shield',
    prompt: 'Оцени позицию защиты по материалам дела: смягчающие обстоятельства и риски.',
  },
];

export function NewCaseScreen({ onFiles, onSuggestion, disabled = false }: { onFiles: (files: File[]) => void; onSuggestion?: (prompt: string) => void; disabled?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    if (disabled) return;
    onFiles(Array.from(e.dataTransfer.files));
  };
  // Pasting a file copied in the OS file manager works anywhere on this screen,
  // not only after focusing the composer (ChatGPT-style global paste).
  useEffect(() => {
    if (disabled) return;
    const onPaste = (e: ClipboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return;
      const pasted = filesFromClipboard(e.clipboardData);
      if (!pasted.length) return;
      e.preventDefault();
      onFiles(pasted);
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [onFiles, disabled]);
  return (
    <div className="fade-in screen-new">
      <LogoMark size={56} color="#141414" />
      <div>
        <h1 className="screen-h1">С каким делом работаем?</h1>
        <p className="screen-lead">Загрузите материалы — получите квалификацию, проект приговора и сверку с практикой.</p>
      </div>
      <button
        type="button"
        className={`btn-soft dropzone ${drag ? 'drag' : ''}`}
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        <span className="dropzone-icon">
          <Icon name="upload" size={26} strokeWidth={1.6} />
        </span>
        <span style={{ fontWeight: 600 }}>Перетащите материалы дела или выберите файлы</span>
        <span className="muted-14">PDF, DOCX, DOTX, TXT, MD · до 50 МБ на файл</span>
      </button>
      <input ref={input} type="file" disabled={disabled} multiple accept={ACCEPT} hidden onChange={(e) => { const files = Array.from(e.target.files ?? []); e.target.value = ''; onFiles(files); }} />
      <div className="sug-grid">
        {SUGGESTIONS.map((s) => (
          <Pressable disabled={disabled} key={s.title} type="button" className="sug" onClick={() => onSuggestion?.(s.prompt)}>
            <IconTile name={s.icon} bg={s.bg} size={36} iconSize={18} />
            <span className="sug-text">
              <span className="sug-title">{s.title}</span>
              <span className="sug-sub">{s.sub}</span>
            </span>
          </Pressable>
        ))}
      </div>
    </div>
  );
}


export function AttachScreen({ files, onRemove, onOpen, disabled = false }: { files: CaseFile[]; onRemove: (index: number) => void; onOpen?: (index: number) => void; disabled?: boolean }) {
  const pages = files.reduce((s, f) => s + f.pages, 0);
  const limited = files.filter((f) => fileReadingWarning(f.recognition));
  return (
    <div className="fade-in screen-attach">
      <div className="attach-head">
        <h1 className="screen-h2">Материалы дела</h1>
        <span className="muted-14">
          {files.length} {plural(files.length, ['файл', 'файла', 'файлов'])} · {pages} {plural(pages, ['страница', 'страницы', 'страниц'])}
        </span>
      </div>
      <ul className="file-list">
        {files.map((f, index) => (
          <li key={`${index}:${f.name}`} className="file-row">
            <FileTile ext={f.ext} size={40} />
            <div className="file-text">
              <button type="button" className="file-name document-filename" disabled={!onOpen} onClick={() => onOpen?.(index)} aria-label={`Открыть ${f.name}`}>{f.name}</button>
              <span className={`file-meta ${fileReadingWarning(f.recognition) ? 'warn' : ''}`}>{fileReadingLabel(f)}</span>
            </div>
            <button type="button" aria-label={`Удалить файл ${f.name}`} className="btn btn-soft btn-icon" disabled={disabled} onClick={() => onRemove(index)}>
              <Icon name="close" size={16} strokeWidth={2} />
            </button>
          </li>
        ))}
      </ul>
      {limited.map((f) => (
        <div key={f.name} className="warn-box" role="note">
          <Icon name="warning" size={18} strokeWidth={2} color="#b54708" />
          <span>
            <strong>{f.name}</strong> {fileReadingWarning(f.recognition)}
          </span>
        </div>
      ))}
    </div>
  );
}

export function ThreadScreen({ analysis, files, thinking, stage, prompt }: { prompt?: string; analysis: CaseAnalysis | null; files: CaseFile[]; thinking: boolean; stage?: string | null }) {
  return (
    <div className="thread">
      <div className="thread-user">
        <div className="bubble">
          <span>{analysis?.prompt || prompt}</span>
          <div className="chips">
            {files.map((f) => (
              <div key={f.name}>
                <FileChip name={f.name} ext={f.ext} />
                <div className="file-meta">{fileReadingLabel(thinking ? {...f, recognition: 'pending'} : f)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
      {thinking ? <Thinking stage={stage} /> : analysis && <Result a={analysis} />}
    </div>
  );
}

// The order of the work: documents, facts, the law, practice, then the recommendation.
const STAGES = ['reading', 'extracting', 'checking', 'searching', 'recommending'];
const LABELS = ['Читаем документы', 'Извлекаем факты', 'Сверяем с законом', 'Ищем похожие дела', 'Готовим рекомендацию'];
// Analyses started before the update report the old stage names.
const LEGACY_STAGES: Record<string, string> = {qualifying: 'extracting'};

/** Memoised on primitive props: the 1 Hz poll re-renders the timeline only when
 *  something actually changed, so the shimmer keeps running between polls. */
export const Thinking = memo(function Thinking({ stage, startedAt }: { stage?: string | null; startedAt?: string }) {
  const seconds = useElapsedSeconds(startedAt);
  const current = STAGES.indexOf(LEGACY_STAGES[stage || ''] || stage || 'reading');
  return (
    <div className="fade-in thread-ai" aria-live="polite">
      <LogoMark size={36} color="#141414" knocking />
      <div className="steps" aria-busy="true">
        <div className="thinking-heading"><span className="steps-title text-shimmer">Анализирую материалы дела</span><span className="analysis-timer text-shimmer" role="timer" aria-label="Прошло времени" aria-live="off">{formatElapsed(seconds)}</span></div>
        {LABELS.map((label, i) => (
          <div key={label} className="step-row">
            {i < current && <Icon name="check" size={16} strokeWidth={2.4} />}
            {i === current && <span className="spin" style={{ margin: '0 2px' }} />}
            {i > current && (
              <span className="pending-slot">
                <span />
              </span>
            )}
            <span className={i < current ? 'step-done' : i === current ? 'step-active' : 'step-pending'}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
});

function Practice({ p }: { p: PracticeComparison }) {
  const s = practiceSummary(p);
  return (
    <section className="practice" aria-label="Сравнение с практикой">
      <div className="eyebrow">Сравнение с практикой</div>
      <div className="practice-headline">{s.headline}</div>
      {s.median && <dl className="practice-stats">
        <div><dt>Медиана</dt><dd>{s.median}</dd></div>
        {s.range && <div><dt>Диапазон 25–75 %</dt><dd>{s.range}</dd></div>}
        {s.spread && <div><dt>Минимум – максимум</dt><dd>{s.spread}</dd></div>}
        <div><dt>Условно (ст. 73)</dt><dd>{shareLabel(p.conditional_share)}</dd></div>
        <div><dt>Ниже низшего (ст. 64)</dt><dd>{shareLabel(p.art64_share)}</dd></div>
        {p.draft_percentile !== null && <div><dt>Перцентиль проекта</dt><dd>{Math.round(p.draft_percentile)}</dd></div>}
      </dl>}
      <p className="practice-note">
        {s.basis}. Сопоставимость определена автоматически по квалификации, обстоятельствам и
        рецидиву; веса оценки ещё не откалиброваны на размеченной выборке.
      </p>
    </section>
  );
}

function CheckList({ checks }: { checks: NonNullable<CaseAnalysis['legalChecks']> }) {
  return <>{checks.map((check,index) => {
          const sourceUrl = legalCheckSourceUrl(check.source);
          return <section key={`${check.norm}-${index}`} className={`legal-check legal-check--${check.status}`}>
            <div className="eyebrow">{check.norm} · {legalCheckStatusLabel(check.status)}</div>
            {check.value && <strong>{check.value.replaceAll('_', ' ')}</strong>}
            <p>{check.explanation}</p>
            {check.evidence.map(quote => <blockquote key={quote}>{quote}</blockquote>)}
            <p className="legal-check-source">
              Источник: {sourceUrl ? <a href={sourceUrl} target="_blank" rel="noreferrer">{sourceUrl}</a> : check.source}
            </p>
          </section>;
        })}</>;
}

function SentenceDetails({ sentence }: {sentence: CaseAnalysis['imposed_sentence']}) {
  if (!sentence) return null;
  return <div className="soft-card" aria-label="Назначенные наказания">
    {sentence.counts.map((c,i) => <div key={i}><strong>{c.qualification}</strong>: {c.punishment}
      {c.additional.map((extra,j) => <div key={j}>Дополнительно: {extra}</div>)}</div>)}
    {sentence.intermediate && <div>Промежуточный итог ({sentence.intermediate_rule}): {sentence.intermediate}</div>}
    {sentence.unserved && <div>Неотбытая часть: {sentence.unserved}</div>}
    {sentence.joined && <div>Присоединено: {sentence.joined}</div>}
    {sentence.prior_judgment_date && <div>Прежний приговор: {sentence.prior_judgment_date}</div>}
    {sentence.credited && <div>Зачёт отбытого: {sentence.credited}</div>}
    {sentence.final && <div>Окончательно ({sentence.aggregation_rule}): {sentence.final}</div>}
    {sentence.final_additional?.map((extra,i) => <div key={i}>Итоговое дополнительное: {extra}</div>)}
  </div>;
}

const SIMILAR_SHOWN = 5;

export function Result({ a, onOpenVerdict }: { a: CaseAnalysis; onOpenVerdict?: (verdict: SimilarVerdict) => void }) {
  const [variant, setVariant] = useState(0);
  const [allSimilar, setAllSimilar] = useState(false);
  const current = a.variants[variant];
  const { documents, pages, seconds } = a.stats;
  const similarRow = (s: SimilarVerdict, i: number) => {
    const body = <>
      <div className="similar-text">
        <span className="similar-title">{s.punishment}</span>
        <span className="similar-meta">
          {s.court} · {s.match}
        </span>
      </div>
      <span className="similar-bar" aria-hidden="true">
        <span style={{ width: `${s.score}%` }} />
      </span>
      <span className="similar-score">{s.score}%</span>
    </>;
    return s.verdict_id != null && onOpenVerdict
      ? <button key={`${i}-${s.punishment}`} type="button" className="similar-row similar-open"
          aria-label={`Открыть приговор: ${s.punishment}, ${s.court}`} onClick={() => onOpenVerdict(s)}>{body}</button>
      : <div key={`${i}-${s.punishment}`} className="similar-row">{body}</div>;
  };
  return (
    <div className="fade-in thread-ai">
      <LogoMark size={36} color="#141414" />
      <div className="result">
        <span className="result-stats">
          {/* Word files have no page count: 0 pages would read as an empty document. */}
          Проанализировано {documents} {plural(documents, ['документ', 'документа', 'документов'])}
          {pages > 0 && <> · {pages} {plural(pages, ['страница', 'страницы', 'страниц'])}</>} · {formatElapsed(seconds)}
        </span>
        {(a.warnings ?? []).map(w => <div key={w} className="warn-box" role="note">{w}</div>)}
        <h2>Разбор</h2>
        <p>{a.fabula}</p>
        <SentenceDetails sentence={a.imposed_sentence} />

        <div className="grid-2">
          {a.qualification && <div className="card">
            <div className="eyebrow">Квалификация</div>
            <div className="card-title">{a.qualification.article}</div>
            <div className="card-sub">{a.qualification.title}</div>
          </div>}
          {a.draft && <div className="card card-col">
            <div className="eyebrow">Проект приговора</div>
            <div className="doc-row">
              <FileTile ext="DOC" size={44} />
              <div style={{ minWidth: 0 }}>
                <div className="doc-name">{a.draft.filename}</div>
                <div className="doc-meta">{a.draft.note}</div>
              </div>
            </div>
            {/* TODO(api): download link */}
            <button type="button" className="btn btn-ink small-btn" disabled title="Экспорт пока не реализован">
              <Icon name="download" size={14} strokeWidth={2.2} />
              Скачать
            </button>
          </div>}
        </div>


        {!a.defendants?.length && <div className="grid-2">
          <div className="soft-card">
            <span className="eyebrow">Смягчающие обстоятельства</span>
            {!a.mitigating.length && <span>Сведения не выделены. Проверьте исходные материалы.</span>}
            {a.mitigating.map((m) => (
              <span key={m.name}>
                <strong>{m.name}</strong> — {m.norm}
              </span>
            ))}
          </div>
          <div className="soft-card">
            <span className="eyebrow">Отягчающие обстоятельства</span>
            <span>{a.aggravating}</span>
            <span className="eyebrow" style={{ marginTop: 4 }}>
              Личность
            </span>
            <span>{a.personality}</span>
          </div>
        </div>}

        <h2>Сверка</h2>
        <CheckList checks={a.legalChecks ?? []} />
        {(a.defendants ?? []).map(person => <section key={person.label} aria-label={person.label}>
          <h3>{person.label}</h3>
          <SentenceDetails sentence={person.imposed_sentence} />
          {person.mitigating.map((c,i) => <p key={i}>{c.name} — {c.norm}{c.quote && <q>{c.quote}</q>}</p>)}
          {person.aggravating && <p>{person.aggravating}</p>}
          <CheckList checks={person.legal_checks} />
          {person.practice_episodes.map((p,i) => <div key={i}><h4>Эпизод {i+1}: {p.qualification}</h4><Practice p={p}/></div>)}
          {person.similar.map((v,i) => v.verdict_id != null && onOpenVerdict
            ? <button key={i} type="button" className="similar-row similar-open" onClick={() => onOpenVerdict(v)}>
                <span>Похожий приговор: {v.punishment} · {v.court} · {v.match}</span>
              </button>
            : <p key={i}>Похожий приговор: {v.punishment} · {v.court} · {v.match}</p>)}
          {person.warnings.map((w,i) => <p key={i} role="note">{w}</p>)}
        </section>)}
        {(a.practiceEpisodes?.length ?? 0) > 0
          ? a.practiceEpisodes!.map((p, i) => <div key={i}>
              <h3>Эпизод {i + 1}: {p.qualification}</h3>
              <p>Рецидив: {({none: 'отсутствует', simple: 'простой', dangerous: 'опасный', especially_dangerous: 'особо опасный'} as Record<string, string>)[p.recidivism ?? ''] ?? 'не установлен в тексте'}</p>
              <Practice p={p} />
            </div>)
          : a.practice && <Practice p={a.practice} />}
        {(!a.defendants?.length || a.scale || current) && <h2>Рекомендация</h2>}
        {a.scale && <SentenceScale scale={a.scale} legend="plain" />}

        {current && <div className="variants">
          <div className="variants-head">
            <span className="eyebrow" style={{ color: '#adadad' }}>
              Варианты наказания
            </span>
            <div role="group" aria-label="Вариант наказания" className="variant-tabs">
              {a.variants.map((v, i) => (
                <button key={v.label} type="button" aria-pressed={variant === i} onClick={() => setVariant(i)}>
                  {v.label}
                </button>
              ))}
            </div>
          </div>
          <span className="variant-title">{current.title}</span>
          <span className="variant-details">{current.details}</span>
          <span className="variant-why">{current.rationale}</span>
        </div>}

        {precedentSourceNote(a.precedentSource) && <div className="warn-box" role="note">{precedentSourceNote(a.precedentSource)}</div>}
        {a.similar.length > 0 && <div className="similar">
          <div className="similar-head">
            <span className="eyebrow">Схожие приговоры</span>
            {a.similar.length > SIMILAR_SHOWN && <button type="button" className="similar-all" aria-expanded={allSimilar}
              onClick={() => setAllSimilar(v => !v)}>{allSimilar ? 'Свернуть' : `Показать все (${a.similar.length})`}</button>}
          </div>
          <p className="similar-hint">Приговоры из базы практики с похожей квалификацией и обстоятельствами; процент — степень сходства. {onOpenVerdict ? 'Нажмите на строку, чтобы открыть текст приговора справа и скачать его.' : ''}</p>
          {a.similar.slice(0, SIMILAR_SHOWN).map((s, i) => similarRow(s, i))}
          {a.similar.length > SIMILAR_SHOWN && (
            // Height-animated reveal keeps «Показать все»/«Свернуть» from jumping;
            // collapsed rows are absent from the DOM and the tab order.
            <AnimatePresence initial={false}>
              {allSimilar && <motion.div key="more" className="similar-more" initial={{height: 0, opacity: 0}} animate={{height: 'auto', opacity: 1}}
                exit={{height: 0, opacity: 0}} transition={{duration: 0.24, ease: [0.22, 1, 0.36, 1]}} style={{overflow: 'hidden'}}>
                {a.similar.slice(SIMILAR_SHOWN).map((s, i) => similarRow(s, i + SIMILAR_SHOWN))}
              </motion.div>}
            </AnimatePresence>
          )}
        </div>

        }

      </div>
    </div>
  );
}
