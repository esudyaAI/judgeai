import type {ButtonHTMLAttributes, ReactNode} from 'react';
import {motion, useReducedMotion} from 'motion/react';

export function BusyButton({pending = false, pendingLabel, children, disabled, ...props}: ButtonHTMLAttributes<HTMLButtonElement> & {pending?: boolean; pendingLabel?: string}) {
  return <Pressable {...props} disabled={disabled || pending} aria-busy={pending || undefined} data-loading={pending || undefined}>
    {pending && <span className="spin" aria-hidden="true" />}{pending ? pendingLabel || children : children}
  </Pressable>;
}
export function StateNotice({children, busy = false, error = false, onRetry}: {children: ReactNode; busy?: boolean; error?: boolean; onRetry?: () => void}) {
  return <div className={`state-notice ${error ? 'warn-box' : ''}`} role={error ? 'alert' : 'status'} aria-busy={busy || undefined}>
    {busy && <span className="spin" aria-hidden="true" />}<span>{children}</span>
    {onRetry && <BusyButton type="button" className="btn btn-line btn-sm" pending={busy} pendingLabel="Загружаем…" onClick={onRetry}>Повторить</BusyButton>}
  </div>;
}
export const surfaceSpring = {type:'spring', stiffness:420, damping:36, mass:0.8} as const;
export function Pressable({children, ...props}: ButtonHTMLAttributes<HTMLButtonElement>) {
  const reduce = useReducedMotion();
  // Pointer press is supplementary: CSS also provides keyboard feedback.
  return <motion.button {...(props as React.ComponentProps<typeof motion.button>)} whileTap={props.disabled || reduce ? undefined : {scale:0.975}} transition={surfaceSpring}>{children}</motion.button>;
}
