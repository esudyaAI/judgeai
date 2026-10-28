import { useState } from 'react';
import { Icon, IconTile } from '../components/Icon';
import { LogoSteps } from '../components/Logo';
import { easeOut, useCountUp, useTicker } from '../hooks/motion';
import { formatMonths } from '../lib/format';
import { Link } from '../router';
import { INFO_PAGES } from '../info/content';
import { AUDIENCE, BENTO_ROWS, FAQ, SIMILAR_BARS, STEPS } from './content';

/** "Для" + rotating 3D drum of audiences (one word every 2.2 s). */
export function Audience() {
  const cur = useTicker(2200, AUDIENCE.length);
  const n = AUDIENCE.length;
  return (
    <section id="audience" className="section">
      <div className="wipe audience">
        <h2 className="audience-h">
          Для<span className="sr-only"> судей, помощников судей, адвокатов, прокуроров, юридических фирм и студентов-юристов.</span>
        </h2>
        <div className="drum" aria-hidden="true">
          {AUDIENCE.map((w, i) => {
            let d = (((i - cur) % n) + n) % n;
            if (d > 2) d -= n;
            const a = Math.abs(d);
            return (
              <span
                key={w}
                className="drum-word"
                style={{
                  transform: `translateY(calc(-50% + ${d * 1.15}em)) rotateX(${-d * 32}deg)`,
                  opacity: a === 0 ? 1 : a === 1 ? 0.5 : 0,
                  color: a === 0 ? '#141414' : '#adadad',
                }}
              >
                {w}
              </span>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function HowItWorks() {
  return (
    <section id="how" className="section">
      <div className="container">
        <h2 className="wipe h2">Три шага от материалов до проекта решения.</h2>
        <div className="rise steps-grid">
          {STEPS.map((s, i) => (
            <div key={s.title} className="step">
              <div className="step-top">
                <LogoSteps lit={i + 1} label={`Шаг ${i + 1}`} />
                <span className="num">{String(i + 1).padStart(2, '0')}</span>
              </div>
              <h3 className="step-title">{s.title}</h3>
              <p className="step-text">{s.text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const clipRight = (q: number) => ({ clipPath: `inset(0 ${((1 - Math.max(0, Math.min(1, q))) * 100).toFixed(2)}% 0 0)` });

function BentoScale() {
  const [ref, bp] = useCountUp<HTMLDivElement>(2200);
  const ba = easeOut((bp - 0.2) / 0.55);
  return (
    <div ref={ref} className="bento-scale">
      <div className="mini-plot">
        <div className="mini-track" />
        <div className="mini-limit" style={{ width: '66.7%', ...clipRight(easeOut(bp / 0.4)) }} />
        <div className="mini-band" style={{ left: '18.3%', width: '21.7%', ...clipRight(easeOut((bp - 0.12) / 0.4)) }} />
        <div className="mini-avg-dot" style={{ transform: `translateX(calc(${(23.3 * ba).toFixed(2)}cqw - 8px))`, opacity: bp > 0.18 ? 1 : 0 }} />
        <div className="mini-avg-label" style={{ transform: `translateX(calc(${(23.3 * ba).toFixed(2)}cqw - 50%))`, opacity: ba > 0.3 ? 1 : 0 }}>
          Среднее · {formatMonths(14 * ba)}
        </div>
      </div>
      <div className="mini-ticks" aria-hidden="true">
        <span>0</span><span>1</span><span>2</span><span>3</span><span>4</span><span>5 лет</span>
      </div>
      <div className="bento-rows">
        {BENTO_ROWS.map((label, i) => {
          const th = 0.5 + i * 0.17;
          const done = bp >= th;
          const active = !done && bp >= th - 0.14;
          return (
            <div key={label} className="bento-row">
              <span style={{ color: done ? '#141414' : '#adadad', transition: 'color .3s ease' }}>{label}</span>
              {done && (
                <span className="d-chip" style={{ display: 'inline-flex' }}>
                  <Icon name="check" size={14} strokeWidth={3} />
                </span>
              )}
              {active && <span className="spin" />}
              {!done && !active && <span className="pending-dash" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SimilarBars() {
  const [ref, sp] = useCountUp<HTMLDivElement>(1500);
  return (
    <div ref={ref} className="sim-bars">
      {SIMILAR_BARS.map(([pct, label], i) => {
        const k = easeOut((sp - i * 0.12) / 0.7);
        return (
          <div key={label} className="sim-row">
            <span className="sim-label">{label}</span>
            <span className="sim-track">
              <span style={{ width: `${pct}%`, ...clipRight(k) }} />
            </span>
            <span className="sim-pct">{Math.round(pct * k)}%</span>
          </div>
        );
      })}
    </div>
  );
}

export function Features() {
  return (
    <section id="features" className="section">
      <div className="container">
        <h2 className="wipe h2" style={{ maxWidth: 760 }}>
          Каждый вывод — с обоснованием.
        </h2>
        <p className="lead">Цифровой судья не просто называет срок. Он показывает, на какие нормы, обстоятельства и приговоры опирается рекомендация.</p>
        <div className="bento">
          <div className="feat rise" style={{ gridColumn: 1, gridRow: 1 }}>
            <IconTile className="tile" name="doc" bg="#0066ff" size={52} iconSize={26} />
            <h3 className="feat-title">Квалификация деяния</h3>
            <p className="feat-text">Определяет статью, часть и пункт УК РФ, отмечает спорные признаки состава.</p>
          </div>
          <div className="feat feat-big rise" style={{ gridColumn: '2 / span 2', gridRow: '1 / span 2' }}>
            <IconTile className="tile" name="scales" bg="#141414" size={52} iconSize={26} />
            <h3 className="feat-title-big">Сверка с законом</h3>
            <p className="feat-text-big">
              Проверяет, что рекомендация укладывается в санкцию статьи и правила назначения наказания ст. 60–64 УК РФ, и показывает, где она находится относительно практики.
            </p>
            <BentoScale />
          </div>
          <div className="feat rise" style={{ gridColumn: 1, gridRow: 2 }}>
            <IconTile className="tile" name="split" bg="#e5480f" size={52} iconSize={26} />
            <h3 className="feat-title">Схожие приговоры</h3>
            <p className="feat-text">Находит решения с той же квалификацией и похожими обстоятельствами.</p>
            <SimilarBars />
          </div>
          <div className="feat rise">
            <IconTile className="tile" name="plusCircle" bg="#0f8a52" size={52} iconSize={26} />
            <h3 className="feat-title">Смягчающие и отягчающие</h3>
            <p className="feat-text">Извлекает обстоятельства из материалов и связывает каждое с нормой ст. 61 и ст. 63 УК РФ.</p>
          </div>
          <div className="feat rise">
            <IconTile className="tile" name="link" bg="#6941e8" size={52} iconSize={26} />
            <h3 className="feat-title">Ссылки на источники</h3>
            <p className="feat-text">Каждый тезис ведёт к странице материала дела, норме закона или тексту приговора.</p>
          </div>
          <div className="feat rise">
            <IconTile className="tile" name="lock" bg="#d4359f" size={52} iconSize={26} />
            <h3 className="feat-title">Конфиденциальность</h3>
            <p className="feat-text">Материалы хранятся в зашифрованном виде и не используются для обучения моделей. [УТОЧНИТЬ ПОЛИТИКУ ХРАНЕНИЯ]</p>
          </div>
        </div>
      </div>
    </section>
  );
}

export function LawHighlight() {
  const [ref, lp] = useCountUp<HTMLDivElement>(2200);
  const lr = easeOut((lp - 0.3) / 0.7);
  const rec = formatMonths(18 * lr);
  return (
    <section className="section">
      <div className="rise law">
        <div className="law-copy">
          <h2 className="wipe h2">Рекомендация в пределах закона.</h2>
          <p className="lead">Цифровой судья показывает санкцию статьи, верхний предел с учётом смягчающих обстоятельств и то, где находится рекомендация и практика по схожим делам.</p>
        </div>
        <div ref={ref} className="law-card">
          <span style={{ fontWeight: 600 }}>Лишение свободы, п. «в» ч. 2 ст. 158</span>
          <div className="law-plot">
            <div className="law-track" />
            <div className="law-limit" style={clipRight(easeOut(lp / 0.45))} />
            <div className="law-band" style={clipRight(easeOut((lp - 0.15) / 0.4))} />
            <div className="law-dot" style={{ transform: `translateX(calc(${(30 * lr).toFixed(2)}cqw - 12px))`, opacity: lp > 0.28 ? 1 : 0 }} />
            <div className="law-label" style={{ transform: `translateX(calc(${(30 * lr).toFixed(2)}cqw - 50%))`, opacity: lr > 0.15 ? 1 : 0 }}>
              {rec}
            </div>
          </div>
          <div className="mini-ticks" aria-hidden="true">
            <span>0</span><span>1 г.</span><span>2 г.</span><span>3 г.</span><span>4 г.</span><span>5 л.</span>
          </div>
          <div className="law-legend">
            <div><span className="law-sw" style={{ background: '#0066ff' }} />Рекомендация — <span className="tnum">{rec}</span></div>
            <div><span className="law-sw" style={{ background: '#cfcfcf' }} />Практика по схожим делам — 11 мес. – 2 г.</div>
            <div><span className="law-sw" style={{ background: '#e0e0e0' }} />Предел по ч. 1 ст. 62 УК РФ — 3 г. 4 мес.</div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function Faq() {
  const [open, setOpen] = useState(0);
  return (
    <section id="faq" className="section">
      <div className="container" style={{ maxWidth: 800 }}>
        <h2 className="wipe h2" style={{ textAlign: 'center' }}>
          Вопросы.
        </h2>
        <div className="stagger faq-list">
          {FAQ.map((f, i) => {
            const isOpen = open === i;
            const id = `faq-${i}`;
            return (
              <div key={f.q} className="rise faq-item">
                <button type="button" className="faq-q focusable" aria-expanded={isOpen} aria-controls={id} onClick={() => setOpen(isOpen ? -1 : i)}>
                  <span>{f.q}</span>
                  <span aria-hidden="true" className="faq-icon" style={{ transform: `rotate(${isOpen ? 45 : 0}deg)` }}>
                    +
                  </span>
                </button>
                <div id={id} className="faq-panel" style={{ gridTemplateRows: isOpen ? '1fr' : '0fr' }} aria-hidden={!isOpen}>
                  <div style={{ overflow: 'hidden', minHeight: 0 }}>
                    <p className={`faq-a ${isOpen ? 'open' : ''}`}>{f.a}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function Cta() {
  return (
    <section className="reveal cta">
      <h2 className="wipe cta-title">Загрузите первое дело.</h2>
      <p className="lead" style={{ marginTop: 20, maxWidth: 560 }}>
        Проект приговора с обоснованием — быстрее, чем вы прочтёте обвинительное заключение.
      </p>
      <Link href="/app/new" className="btn btn-ink btn-lg" style={{ marginTop: 32 }}>
        Попробовать
      </Link>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="foot">
      <div className="container foot-inner">
        <div className="foot-top">
          <div className="foot-brand">
            <span className="foot-word">Цифровой судья</span>
            <span className="foot-muted" style={{ maxWidth: 360 }}>
              ИИ-помощник для подготовки проектов судебных решений.
            </span>
          </div>
          <div className="foot-cols">
            <div className="foot-col">
              <span style={{ fontWeight: 600 }}>Продукт</span>
              <a href="#how">Как работает</a>
              <a href="#audience">Для кого</a>
              <a href="#features">Почему мы</a>
            </div>
            <div className="foot-col">
              <span style={{ fontWeight: 600 }}>О сервисе и данных</span>
              {INFO_PAGES.map(page => <Link key={page.path} href={page.path}>{page.label}</Link>)}
            </div>
          </div>
        </div>
        <p className="foot-muted" style={{ fontSize: 12 }}>
          © 2026 Цифровой судья
        </p>
      </div>
    </footer>
  );
}
