/** Skeleton of the case thread shown while messages load. The 180 ms delayed
 *  fade-in keeps fast loads from flashing a skeleton for a single frame. */
export function CaseSkeleton() {
  return (
    <div className="case-skeleton" role="status" aria-busy="true">
      <span className="sr-only">Загружаем дело…</span>
      <div className="sk-thread">
        <div className="sk-turn-user">
          <div className="sk-bubble">
            <span className="sk-line w-60" />
            <span className="sk-line w-30" />
            <div className="sk-chips"><span className="sk-chip" /><span className="sk-chip" /></div>
          </div>
        </div>
        <div className="sk-turn-ai">
          <span className="sk-avatar" />
          <div className="sk-reply">
            <span className="sk-line sk-title w-45" />
            <span className="sk-line w-90" />
            <span className="sk-line w-78" />
            <span className="sk-line w-85" />
            <span className="sk-line w-60" />
          </div>
        </div>
      </div>
    </div>
  );
}
