interface InertTarget {inert: boolean}
const owners = new WeakMap<InertTarget, {count: number; original: boolean}>();
/** Overlapping modal surfaces release only their own background lock. */
export function acquireInert(target: InertTarget): () => void {
  const entry = owners.get(target) || {count:0,original:target.inert};
  entry.count += 1; owners.set(target,entry); target.inert = true;
  let released = false;
  return () => {
    if (released) return;
    released = true; entry.count -= 1;
    if (!entry.count) { target.inert = entry.original; owners.delete(target); }
  };
}
