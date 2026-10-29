/**
 * Fast "printing" of a suggestion into the composer field (ChatGPT-style fill):
 * the full text appears within ~0.2–0.5 s. Framework-independent and injectable
 * so the pacing and cancellation can be unit-tested without a DOM.
 */

export interface TypewriterScheduler {
  schedule: (callback: (now: number) => void) => number;
  cancel: (handle: number) => void;
  now: () => number;
}

const rafScheduler: TypewriterScheduler = {
  schedule: (callback) => requestAnimationFrame(callback),
  cancel: (handle) => cancelAnimationFrame(handle),
  now: () => performance.now(),
};

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export interface Typewriter {
  /** Start printing `text`; cancels any run in progress. */
  print: (text: string, options?: { instant?: boolean }) => void;
  /** Stop the current run, keeping whatever was already printed. */
  cancel: () => void;
}

export function createTypewriter(setValue: (value: string) => void, scheduler: TypewriterScheduler = rafScheduler): Typewriter {
  let handle = 0;
  const cancel = () => {
    if (handle) {
      scheduler.cancel(handle);
      handle = 0;
    }
  };
  return {
    cancel,
    print(text, options) {
      cancel();
      if (!text || options?.instant) {
        setValue(text);
        return;
      }
      // Constant total duration: long prompts are not slower to watch.
      const totalMs = Math.min(500, Math.max(160, text.length * 8));
      const startedAt = scheduler.now();
      let printed = 0;
      const tick = (now: number) => {
        handle = 0;
        const progress = Math.min(1, (now - startedAt) / totalMs);
        const count = progress >= 1 ? text.length : Math.max(1, Math.round(text.length * progress));
        if (count > printed) {
          printed = count;
          setValue(text.slice(0, count));
        }
        if (progress < 1) handle = scheduler.schedule(tick);
        else setValue(text);
      };
      handle = scheduler.schedule(tick);
    },
  };
}
