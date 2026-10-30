/**
 * A suggestion card's text lands in the composer so the user can keep typing:
 * it ends with exactly one space, separating the preset prompt from what the
 * user adds. Pure and exported for tests; the DOM side (caret and horizontal
 * scroll pinned to the end) lives in Cabinet.
 */
export function suggestionFill(text: string): string {
  if (!text || text.endsWith(' ')) return text;
  return `${text} `;
}
