import { mockAnalysis } from '../api/mock';
import type { FileExt } from '../api/types';
import { FileChip, FileTile } from '../components/FileTile';
import { Icon } from '../components/Icon';
import { LogoMark } from '../components/Logo';
import { SentenceScale } from '../components/SentenceScale';
import { easeOut, useInView, useTimeline } from '../hooks/motion';

// Timeline (ms) copied from Main.dc.html: files 0.5–1.5s, typing 2.5–4.5s, send 5s,
// analysis steps from 5.5s every 0.9s, answer cards from 9.3s, loop at 15s.
const TOTAL = 15000;
const SEND = 5000;
const PROMPT = 'Подготовь проект приговора. Подсудимый признал вину, ущерб возмещён.';
const FILES: [string, FileExt, number][] = [
  ['Обвинительное заключение.pdf', 'PDF', 500],
  ['Протоколы допросов.pdf', 'PDF', 1000],
  ['Характеристика.docx', 'DOC', 1500],
];
const STEP_LABELS = ['Читаю материалы — 142 страницы', 'Квалифицирую деяние', 'Ищу схожие приговоры', 'Сверяю с санкцией статьи'];

export function Demo() {
  const [ref, playing] = useInView<HTMLElement>(0.35);
  const t = useTimeline(playing, TOTAL);

  const files = t < SEND + 600 ? FILES.filter(([, , at]) => t >= at).map(([name, ext, at]) => ({ name, ext, p: easeOut((t - at) / 900) })) : [];
  const chipsOpen = t >= 500 && t < SEND;
  const typing = t >= 2500 && t < SEND;
  const typedLen = typing ? Math.min(PROMPT.length, Math.round(PROMPT.length * easeOut((t - 2500) / 2000))) : 0;
  const ready = typing && typedLen > 0;
  const pressed = t >= 4700 && t < SEND;
  const steps = STEP_LABELS.map((label, i) => {
    const start = 5500 + i * 900;
    return { label, start, done: t >= start + 900, active: t >= start && t < start + 900 };
  }).filter((s) => t >= s.start);
  const sent = t >= SEND;
  const thinking = t >= 5300 && t < 9300;
  const answer = t >= 9300;
  const status = answer ? 'Проект готов' : sent ? 'Анализ' : 'Черновик';

  return (
    <section id="demo" ref={ref} className="hero-in demo-section" style={{ animationDelay: '.65s' }} aria-label="Как выглядит работа с делом">
      <div className="demo-frame">
        <div className="demo-window">
          <div className="demo-head">
            <span className="demo-title">Новое дело</span>
            <span className="badge" data-loading={sent && !answer || undefined} aria-live="polite">
              {status}
            </span>
          </div>

          <div className="demo-body">
            {sent && (
              <div className="d-in demo-user">
                <div className="bubble">
                  <span>{PROMPT}</span>
                  <div className="chips">
                    {FILES.map(([name, ext]) => (
                      <FileChip key={name} name={name} ext={ext} />
                    ))}
                  </div>
                </div>
              </div>
            )}

            {thinking && (
              <div className="d-in demo-thinking">
                <LogoMark size={36} color="#141414" knocking />
                <div className="steps">
                  <span className="steps-title">Анализирую материалы дела</span>
                  {steps.map((s) => (
                    <div key={s.label} className="d-in step-row" data-loading={s.active || undefined}>
                      {s.done && <Icon name="check" size={16} strokeWidth={2.4} />}
                      {s.active && <span className="spin" />}
                      <span className={s.done ? 'step-done' : 'step-active'}>{s.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {answer && (
              <>
                <div className="d-in demo-done">
                  <Icon name="check" size={14} strokeWidth={2.4} color="#707070" />
                  Анализ завершён · 4 этапа
                </div>
                <div className="demo-answer">
                  <LogoMark size={36} color="#141414" />
                  <div className="answer-grid">
                    {t >= 9500 && (
                      <div className="d-in card">
                        <div className="eyebrow">Квалификация</div>
                        <div className="card-title">п. «в» ч. 2 ст. 158 УК РФ</div>
                        <div className="card-sub">Кража с причинением значительного ущерба гражданину</div>
                      </div>
                    )}
                    {t >= 10000 && (
                      <div className="d-in card card-col">
                        <div className="eyebrow">Проект приговора</div>
                        <div className="doc-row">
                          <FileTile ext="DOC" size={44} />
                          <div style={{ minWidth: 0 }}>
                            <div className="doc-name">Приговор.docx</div>
                            <div className="doc-meta">12 стр. · все части приговора</div>
                          </div>
                        </div>
                        <span className="fake-btn">
                          <Icon name="download" size={14} strokeWidth={2.2} color="#ffffff" />
                          Скачать
                        </span>
                      </div>
                    )}
                    {t >= 10500 && (
                      <div className="d-in span-all">
                        <SentenceScale scale={mockAnalysis.scale!} animated legend="swatch" />
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="demo-composer-wrap">
            <div className="composer composer-demo" aria-hidden="true">
              <div className={`chips-wrap ${chipsOpen ? 'open' : ''}`}>
                <div className="chips" style={{ paddingBottom: 10 }}>
                  {files.map((f) => (
                    <span key={f.name} className="d-chip upload-chip" data-loading={f.p < 1 || undefined}>
                      <FileTile ext={f.ext} size={32} />
                      <span className="upload-body">
                        <span className="upload-name">{f.name}</span>
                        <span className="upload-bar">
                          <span style={{ width: `${(f.p * 100).toFixed(1)}%` }} />
                        </span>
                      </span>
                    </span>
                  ))}
                </div>
              </div>
              <div className="composer-row">
                <span className="composer-btn">
                  <Icon name="clip" size={18} />
                </span>
                <span className={`composer-input ${typedLen > 0 ? 'filled' : ''}`}>
                  {typedLen > 0 ? PROMPT.slice(0, typedLen) : 'Опишите задачу или перетащите материалы дела'}
                  {typing && <span className="caret" />}
                </span>
                <span className={`composer-send ${ready ? 'ready' : ''}`} style={{ transform: `scale(${pressed ? 0.86 : 1})` }}>
                  <Icon name="arrowUp" size={18} strokeWidth={2} color="#ffffff" />
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
