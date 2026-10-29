import type { Message } from '../api/client';

/**
 * Cheap change-detection for the 1 Hz message poll: while an analysis runs,
 * most responses are byte-identical, and re-creating the messages state would
 * re-render the whole timeline every second and starve the paint-driven
 * shimmer animation. Only a changed status/stage/attachment triggers a render.
 * `result` is covered by the status transition that writes it.
 */
export function messagesFingerprint(messages: Message[]): string {
  return messages
    .map((m) => `${m.id}:${m.status}:${m.stage ?? ''}:${m.error ?? ''}:${m.content ? m.content.length : 0}:${m.result ? 'r' : ''}`
      + m.attachments.map((a) => `${a.extraction_status}:${a.page_count ?? 0}`).join(','))
    .join('|');
}
