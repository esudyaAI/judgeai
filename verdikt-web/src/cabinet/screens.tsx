import { useRef, useState, type DragEvent } from 'react';
import type { CaseAnalysis, CaseFile, PracticeComparison, SimilarVerdict } from '../api/types';
import { FileChip, FileTile } from '../components/FileTile';
import { Icon, IconTile, type IconName } from '../components/Icon';
import { LogoMark } from '../components/Logo';
import { SentenceScale } from '../components/SentenceScale';
import { plural } from '../lib/format';
import { fileReadingLabel, fileReadingWarning } from './fileReadingPresentation';
import { ACCEPT } from './Composer';
import { formatElapsed, useElapsedSeconds } from './useElapsedSeconds';
import { legalCheckSourceUrl, legalCheckStatusLabel } from './legalCheckPresentation';
import { practiceSummary, precedentSourceNote, shareLabel } from './practicePresentation';

const SUGGESTIONS: [string, string, string, IconName][] = [
  ['Подготовить проект приговора', 'Квалификация, наказание и текст', '#0066ff', 'doc'],
  ['Проверить квалификацию', 'Статья, часть и спорные признаки', '#141414', 'scales'],
  ['Найти схожие приговоры', 'Практика по той же статье', '#e5480f', 'cmp'],
  ['Оценить позицию защиты', 'Смягчающие обстоятельства и риски', '#0f8a52', 'shield'],
];

export function NewCaseScreen({ onFiles }: { onFiles: (list: FileList | null) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    onFiles(e.dataTransfer.files);
  };
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
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
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
      <input ref={input} type="file" multiple accept={ACCEPT} hidden onChange={(e) => onFiles(e.target.files)} />
      <div className="sug-grid">
        {SUGGESTIONS.map(([title, text, bg, icon]) => (
          <button key={title} type="button" className="sug" onClick={() => onFiles(null)}>
            <IconTile name={icon} bg={bg} size={36} iconSize={18} />
            <span className="sug-text">
              <span className="sug-title">{title}</span>
              <span className="sug-sub">{text}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}


export function AttachScreen({ files, onRemove, onOpen }: { files: CaseFile[]; onRemove: (name: string) => void; onOpen?: (index: number) => void }) {
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
          <li key={f.name} className="file-row">
            <FileTile ext={f.ext} size={40} />
            <div className="file-text">
              <button type="button" className="file-name document-filename" onClick={() => onOpen?.(index)} aria-label={`Открыть ${f.name}`}>{f.name}</button>
              <span className={`file-meta ${fileReadingWarning(f.recognition) ? 'warn' : ''}`}>{fileReadingLabel(f)}</span>
            </div>
            <button type="button" aria-label={`Удалить файл ${f.name}`} className="btn btn-soft btn-icon" onClick={() => onRemove(f.name)}>
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

interface Step {
  label: string;
  done: boolean;
  active: boolean;
}

export function ThreadScreen({ analysis, files, thinking, steps, prompt }: { prompt?: string; analysis: CaseAnalysis | null; files: CaseFile[]; thinking: boolean; steps: Step[] }) {
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
      {thinking ? <Thinking steps={steps} /> : analysis && <Result a={analysis} />}
    </div>
  );
}

export function Thinking({ steps, startedAt }: { steps: Step[]; startedAt?: string }) {
  const seconds = useElapsedSeconds(startedAt);
  return (
    <div className="fade-in thread-ai" aria-live="polite">
      <LogoMark size={36} color="#141414" knocking />
      <div className="steps" aria-busy="true">
        <div className="thinking-heading"><span className="steps-title text-shimmer">Анализирую материалы дела</span><span className="analysis-timer text-shimmer" role="timer" aria-label="Прошло времени" aria-live="off">{formatElapsed(seconds)}</span></div>
        {steps.map((s) => (
          <div key={s.label} className="step-row">
            {s.done && <Icon name="check" size={16} strokeWidth={2.4} />}
            {s.active && <span className="spin" style={{ margin: '0 2px' }} />}
            {!s.done && !s.active && (
              <span className="pending-slot">
                <span />
              </span>
            )}
            <span className={s.done ? 'step-done' : s.active ? 'step-active' : 'step-pending'}>{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

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

const SIMILAR_SHOWN = 5;

export function Result({ a, onOpenVerdict }: { a: CaseAnalysis; onOpenVerdict?: (verdict: SimilarVerdict) => void }) {
  const [variant, setVariant] = useState(0);
  const [allSimilar, setAllSimilar] = useState(false);
  const current = a.variants[variant];
  const { documents, pages, seconds } = a.stats;
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


        <div className="grid-2">
          <div className="soft-card">
            <span className="eyebrow">Смягчающие обстоятельства</span>
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
        </div>

        <h2>Сверка</h2>
        {(a.legalChecks ?? []).map(check => {
          const sourceUrl = legalCheckSourceUrl(check.source);
          return <section key={check.norm} className={`legal-check legal-check--${check.status}`}>
            <div className="eyebrow">{check.norm} · {legalCheckStatusLabel(check.status)}</div>
            {check.value && <strong>{check.value.replaceAll('_', ' ')}</strong>}
            <p>{check.explanation}</p>
            {check.evidence.map(quote => <blockquote key={quote}>{quote}</blockquote>)}
            <p className="legal-check-source">
              Источник: {sourceUrl ? <a href={sourceUrl} target="_blank" rel="noreferrer">{sourceUrl}</a> : check.source}
            </p>
          </section>;
        })}
        {(a.practiceEpisodes?.length ?? 0) > 0
          ? a.practiceEpisodes!.map((p, i) => <div key={i}>
              <h3>Эпизод {i + 1}: {p.qualification}</h3>
              <p>Рецидив: {({none: 'отсутствует', simple: 'простой', dangerous: 'опасный', especially_dangerous: 'особо опасный'} as Record<string, string>)[p.recidivism ?? ''] ?? 'не установлен в тексте'}</p>
              <Practice p={p} />
            </div>)
          : a.practice && <Practice p={a.practice} />}
        <h2>Рекомендация</h2>
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
          {(allSimilar ? a.similar : a.similar.slice(0, SIMILAR_SHOWN)).map((s, i) => {
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
            const verdictId = s.verdict_id;
            return verdictId != null && onOpenVerdict
              ? <button key={`${i}-${s.punishment}`} type="button" className="similar-row similar-open"
                  aria-label={`Открыть приговор: ${s.punishment}, ${s.court}`} onClick={() => onOpenVerdict(s)}>{body}</button>
              : <div key={`${i}-${s.punishment}`} className="similar-row">{body}</div>;
          })}
        </div>

        }

      </div>
    </div>
  );
}
