import { useEffect } from 'react';
import { AuthGate } from './auth/AuthGate';
import { Cabinet, parseCabinetPath } from './cabinet/Cabinet';
import { Landing } from './landing/Landing';
import { usePath } from './router';
import { InfoPage } from './info/InfoPage';
import { findInfoPage } from './info/content';

export function App() {
  const [path, go] = usePath();
  const infoPage = findInfoPage(path);
  const isCabinet = path === '/app' || path.startsWith('/app/');

  useEffect(() => {
    document.title = infoPage ? `${infoPage.label} — Цифровой судья` : isCabinet ? 'Цифровой судья — личный кабинет' : 'Цифровой судья — ИИ-помощник судьи';
  }, [isCabinet, infoPage]);

  useEffect(() => { if (infoPage) window.scrollTo(0, 0); }, [infoPage]);

  if (infoPage) return <InfoPage page={infoPage} />;

  if (isCabinet) return <AuthGate>{(user, signOut) => <Cabinet key={user.id} route={parseCabinetPath(path)} onNavigate={go} user={user} onSignOut={signOut} />}</AuthGate>;
  return <Landing />;
}
