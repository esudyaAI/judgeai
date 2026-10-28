import { Link } from '../router';
import { LogoMark } from '../components/Logo';
import { INFO_PAGES, type InfoPageContent } from './content';
import './info.css';

export function InfoPage({page}: {page: InfoPageContent}) {
  return <div className="info-page">
    <header className="info-header">
      <Link href="/" className="info-brand"><LogoMark size={28} /><span>Цифровой судья</span></Link>
      <Link href="/app" className="btn btn-ink btn-sm">Личный кабинет</Link>
    </header>
    <main id="info-main" className="info-layout">
      <aside className="info-sidebar">
        <Link href="/" className="info-back">← На главную</Link>
        <nav aria-label="О сервисе и данных">
          {INFO_PAGES.map(item => <Link key={item.path} href={item.path} aria-current={item.path === page.path ? 'page' : undefined}>{item.label}</Link>)}
        </nav>
      </aside>
      <article className="info-article">
        <p className="info-eyebrow">Информация о сервисе · 28 октября 2026</p>
        <h1>{page.title}</h1>
        <p className="info-intro">{page.intro}</p>
        {page.path === '/privacy' && <p className="info-notice" role="note">Информация об обработке данных уточняется. Реквизиты оператора и контакт для обращений будут добавлены перед публикацией.</p>}
        {page.sections.map((section, index) => <section key={section.title} aria-labelledby={`info-section-${index}`}>
          <h2 id={`info-section-${index}`}>{section.title}</h2>
          {section.paragraphs.map(text => <p key={text}>{text}</p>)}
        </section>)}
        <footer className="info-article-footer"><Link href="/">Вернуться на главную →</Link></footer>
      </article>
    </main>
    <footer className="info-footer">© 2026 Цифровой судья · Окончательное решение принимает человек.</footer>
  </div>;
}
