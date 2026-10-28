import type { CSSProperties } from 'react';
import { Icon } from '../components/Icon';
import { Link } from '../router';
import { ACCENTS, CLOUD, CRIMES } from './content';

const HEADLINE: [string, number][] = [
  ['Приговор', 0.05], ['по', 0.13], ['материалам', 0.21], ['дела', 0.29],
];
const HEADLINE_2: [string, number][] = [
  ['за', 0.45], ['минуты.', 0.53],
];

function Words({ words }: { words: [string, number][] }) {
  return (
    <>
      {words.map(([w, d], i) => (
        <span key={w}>
          <span className="wl">
            <span className="w" style={{ animationDelay: `${d}s` }}>
              {w}
            </span>
          </span>
          {i < words.length - 1 ? ' ' : null}
        </span>
      ))}
    </>
  );
}

export function Hero() {
  return (
    <section id="top" className="hero">
      <div className="cloud" aria-hidden="true">
        {CLOUD.map(([left, top, size, c, icon, rot, delay]) => (
          <span
            key={`${left}-${top}`}
            className="ftile floaty"
            style={
              {
                position: 'absolute',
                left: `calc(${left}% - ${size / 2}px)`,
                top,
                width: size,
                height: size,
                background: ACCENTS[c],
                '--r': `${rot}deg`,
                animationDelay: `${delay}s, ${delay}s`,
              } as CSSProperties
            }
          >
            <Icon name={icon} size={Math.round(size * 0.46)} color="#ffffff" />
          </span>
        ))}
      </div>
      <h1 className="hero-title">
        <Words words={HEADLINE} />
        <br />
        <Words words={HEADLINE_2} />
      </h1>
      <p className="hero-in hero-lead" style={{ animationDelay: '.7s' }}>
        Загрузите материалы — «Цифровой судья» квалифицирует деяние, найдёт схожие приговоры, сверит рекомендацию с санкцией статьи и объяснит каждый вывод.
      </p>
      <div className="hero-in hero-cta" style={{ animationDelay: '.85s' }}>
        <Link href="/app/new" className="btn btn-ink btn-lg">
          Загрузить дело
        </Link>
        <a href="#how" className="btn btn-line btn-lg">
          Как это работает
        </a>
      </div>
    </section>
  );
}

export function Marquee() {
  const items = [...CRIMES, ...CRIMES];
  return (
    <section className="hero-in marquee-section" style={{ animationDelay: '.5s' }} aria-label="Категории дел">
      <div className="marquee">
        <div className="track">
          {items.map(([label, icon], i) => (
            <span key={`${label}-${i}`} className="marquee-item" aria-hidden={i >= CRIMES.length ? true : undefined}>
              <span className="ftile" style={{ width: 48, height: 48, background: '#141414' }}>
                <Icon name={icon} size={24} color="#ffffff" />
              </span>
              <span className="marquee-label">{label}</span>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
