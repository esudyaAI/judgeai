/**
 * Browser «back» closes overlays (mobile drawer, dialogs, the mobile document
 * panel) instead of navigating away — the expected behavior on Android/WebView.
 *
 * Opening an overlay pushes a same-URL sentinel history entry; a back press pops
 * it and closes the topmost overlay. UI-driven closes pop the sentinel via
 * history.back() when it is still on top; a sentinel buried under a later
 * navigation is dropped silently — it shares the URL of the page beneath it,
 * so a later back press still lands where the user expects. Chosen over hash
 * markers («#dialog») so the URL never changes and no scroll-jump can occur.
 *
 * The stack keeps nested overlays ordered: back closes the topmost first
 * (e.g. the delete dialog above the open drawer).
 */

let counter = 0;
const stack: { id: number; close: () => void }[] = [];
let listening = false;

function stopListening() {
  if (!stack.length && listening) {
    window.removeEventListener('popstate', onPopState);
    listening = false;
  }
}

function onPopState() {
  const top = stack.pop();
  stopListening();
  top?.close();
}

export function registerOverlayBack(close: () => void): () => void {
  const id = ++counter;
  if (!listening) {
    window.addEventListener('popstate', onPopState);
    listening = true;
  }
  history.pushState({ overlayBack: id }, '');
  stack.push({ id, close });
  return () => {
    const index = stack.findIndex((entry) => entry.id === id);
    if (index < 0) return; // already consumed by a back press
    if ((history.state as { overlayBack?: number } | null)?.overlayBack === id) {
      // Sentinel on top: pop it, keeping history balanced. The popstate handler
      // re-runs close(), which is already in progress here and must be idempotent.
      history.back();
      return;
    }
    stack.splice(index, 1);
    stopListening();
  };
}
