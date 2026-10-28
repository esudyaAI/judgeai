import { useEffect, useState, type ReactNode } from 'react';
import { auth, AuthenticationError, type AuthUser } from '../api/client';
import { LogoMark } from '../components/Logo';
import './auth.css';

export function AuthGate({children}: {children: (user: AuthUser, signOut: () => Promise<void>) => ReactNode}) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(true);
  const [retry, setRetry] = useState(0);
  const [connectionError, setConnectionError] = useState('');
  useEffect(() => {
    let current = true;
    setChecking(true);
    const expired = () => { setUser(null); setConnectionError(''); };
    window.addEventListener('judgeai:unauthorized', expired);
    void auth.me().then(next => { if (current) { setUser(next); setConnectionError(''); } })
      .catch(error => { if (current && !(error instanceof AuthenticationError)) setConnectionError('Нет связи с сервером. Попробуйте ещё раз.'); })
      .finally(() => { if (current) setChecking(false); });
    return () => { current = false; window.removeEventListener('judgeai:unauthorized', expired); };
  }, [retry]);

  if (checking) return <div className="auth-status" role="status">Проверяем сеанс…</div>;
  if (connectionError) return <div className="auth-status" role="alert"><p>{connectionError}</p><button className="btn btn-ink" onClick={() => setRetry(n => n + 1)}>Повторить</button></div>;
  if (user) return children(user, async () => { await auth.logout(); setUser(null); });
  return <SignIn onSignedIn={setUser} />;
}

type Mode = 'login' | 'register';

const TEXT: Record<Mode, { title: string; intro: string; submit: string; pending: string; switchHint: string; switchTo: string }> = {
  login: {
    title: 'Вход в личный кабинет',
    intro: 'Проверяйте проекты приговоров и продолжайте работу с делами в одном месте.',
    submit: 'Войти', pending: 'Входим…',
    switchHint: 'Нет аккаунта?', switchTo: 'Зарегистрироваться',
  },
  register: {
    title: 'Регистрация',
    intro: 'Создайте аккаунт — дела и анализы видны только вам.',
    submit: 'Зарегистрироваться', pending: 'Создаём аккаунт…',
    switchHint: 'Уже есть аккаунт?', switchTo: 'Войти',
  },
};

function SignIn({onSignedIn}: {onSignedIn: (user: AuthUser) => void}) {
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const text = TEXT[mode];
  const registering = mode === 'register';
  return <main className="auth-page">
    <a href="/" className="auth-brand"><LogoMark size={30} /><span>Цифровой судья</span></a>
    <section className="auth-panel" aria-labelledby="auth-title">
      <p className="auth-eyebrow">Личный кабинет</p>
      <h1 id="auth-title">{text.title}</h1>
      <p className="auth-intro">{text.intro}</p>
      <form onSubmit={async event => {
        event.preventDefault();
        if (pending) return;
        setPending(true); setError('');
        try {
          const user = registering ? await auth.register(username, password) : await auth.login(username, password);
          setPassword(''); onSignedIn(user);
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : 'Не удалось выполнить запрос');
          setPassword('');
        } finally { setPending(false); }
      }}>
        <label htmlFor="username">Имя пользователя</label>
        <input id="username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false}
          required minLength={registering ? 3 : 1} maxLength={80} value={username}
          onChange={event => setUsername(event.target.value)} disabled={pending}
          aria-describedby={registering ? 'username-hint' : undefined} />
        {registering && <p id="username-hint" className="auth-hint">Латинские буквы, цифры, точка, дефис или подчёркивание; от 3 символов.</p>}
        <label htmlFor="password">Пароль</label>
        <input id="password" name="password" type="password" autoComplete={registering ? 'new-password' : 'current-password'} required
          minLength={registering ? 12 : 1} maxLength={1024} value={password} onChange={event => setPassword(event.target.value)} disabled={pending}
          aria-describedby={[registering ? 'password-hint' : '', error ? 'auth-error' : ''].filter(Boolean).join(' ') || undefined} />
        {registering && <p id="password-hint" className="auth-hint">Не меньше 12 символов.</p>}
        {error && <p id="auth-error" className="auth-error" role="alert">{error}</p>}
        <button type="submit" className="btn btn-ink btn-md" disabled={pending}>{pending ? text.pending : text.submit}</button>
      </form>
      <p className="auth-help">
        {text.switchHint}{' '}
        <button type="button" className="auth-switch" disabled={pending}
          onClick={() => { setMode(registering ? 'login' : 'register'); setError(''); setPassword(''); }}>{text.switchTo}</button>
      </p>
    </section>
    <footer className="auth-footer">Второе мнение для взвешенного решения.</footer>
  </main>;
}
