/** Client-side availability only; the server remains the authority for validation. */
export function canAuthenticate(mode: 'login' | 'register', username: string, password: string) {
  if (!username.trim() || !password || username.length > 80 || password.length > 1024) return false;
  return mode === 'login' || (/^[A-Za-z0-9_.-]{3,80}$/.test(username) && password.length >= 12);
}
export function canChangePassword(current: string, next: string, repeated: string) {
  return Boolean(current) && current.length <= 1024 && next.length >= 12 && next.length <= 1024 && next === repeated;
}
