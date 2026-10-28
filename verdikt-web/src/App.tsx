import { useEffect } from 'react';
import { AuthGate } from './auth/AuthGate';
import { Cabinet, parseCabinetPath } from './cabinet/Cabinet';
import { Landing } from './landing/Landing';
import { usePath } from './router';

export function App() {
  const [path, go] = usePath();
  const isCabinet = path === '/app' || path.startsWith('/app/');

  useEffect(() => {
    document.title = isCabinet ? 'Цифровой судья — личный кабинет' : 'Цифровой судья — ИИ-помощник судьи';
  }, [isCabinet]);

  if (isCabinet) return <AuthGate>{(user, signOut) => <Cabinet key={user.id} route={parseCabinetPath(path)} onNavigate={go} user={user} onSignOut={signOut} />}</AuthGate>;
  return <Landing />;
}
