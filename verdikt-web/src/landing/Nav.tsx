import { useRef, useState, type MouseEvent } from 'react';
import { LogoMark } from '../components/Logo';
import { Link } from '../router';

interface Pill {
  l: number;
  r: number;
  t: number;
  b: number;
}

const LINKS = [
  ['#audience', 'Для кого'],
  ['#how', 'Как работает'],
  ['#features', 'Почему мы'],
  ['#faq', 'Вопросы'],
] as const;

/**
 * Floating nav with a "flowing pill" hover: the trailing edge lags behind the
 * leading one, so the pill stretches toward the target and then catches up.
 */
export function Nav() {
  const [pill, setPill] = useState<Pill | null>(null);
  const [dir, setDir] = useState(1);
  const last = useRef<Pill | null>(null);

  const enter = (e: MouseEvent<HTMLAnchorElement>) => {
    const a = e.currentTarget;
    const box = a.parentElement;
    if (!box) return;
    const next = { l: a.offsetLeft, r: box.clientWidth - a.offsetLeft - a.offsetWidth, t: a.offsetTop, b: box.clientHeight - a.offsetTop - a.offsetHeight };
    const prev = pill ?? last.current;
    last.current = next;
    setDir(prev && next.l < prev.l ? -1 : 1);
    setPill(next);
  };

  const lead = '.22s var(--ease-out)';
  const trail = '.3s var(--ease-out) .05s';
  const pos = pill ?? last.current;
  const pillStyle = {
    transition: `left ${dir > 0 ? trail : lead}, right ${dir > 0 ? lead : trail}, top .3s ease, bottom .3s ease, opacity .25s ease`,
    opacity: pill ? 1 : 0,
    left: pos?.l ?? 0,
    right: pos?.r ?? 0,
    top: pill ? pill.t : 0,
    bottom: pill ? pill.b : 0,
  };

  return (
    <div className="nav-wrap">
      <nav aria-label="Основная навигация" className="nav">
        <a href="#top" className="nav-brand">
          <LogoMark size={32} color="#141414" />
          <span>Цифровой судья</span>
        </a>
        <div className="nav-links" onMouseLeave={() => setPill(null)}>
          <span aria-hidden="true" className="nav-pill" style={pillStyle} />
          {LINKS.map(([href, label]) => (
            <a key={href} href={href} className="nav-link" onMouseEnter={enter}>
              {label}
            </a>
          ))}
          <Link href="/app" className="nav-link" onMouseEnter={enter}>
            Войти
          </Link>
          <Link href="/app/new" className="btn btn-ink btn-md nav-cta">
            Попробовать
          </Link>
        </div>
      </nav>
    </div>
  );
}
