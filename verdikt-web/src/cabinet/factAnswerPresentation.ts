/**
 * T45.4 — how the chat shows an answer whose facts were read by code (T45.1–T45.3).
 *
 * The backend marks such a message with `fact_answer`; the note says which facts the
 * program read and whether a language model only reworded them. Only these answers turn their
 * addresses into links: their sources are written by code from the database, while a model's
 * free text could name an address nobody checked.
 */

import type { FactAnswer } from '../api/client';

export interface TextSegment { text: string; href?: string }

const PRACTICE = 'Цифры посчитаны программой по приговорам базы практики.';
const WORDED = 'Текст сформулировала языковая модель; каждое число в нём сверено с расчётом.';

export function factAnswerNote(answer: FactAnswer | null | undefined): string | null {
  if (!answer) return null;
  if (answer.kind === 'practice') {
    return [PRACTICE, answer.worded_by_model ? WORDED : '', 'Источники — ниже.'].filter(Boolean).join(' ');
  }
  if (answer.kind === 'sanction') {
    const worded = answer.worded_by_model ? ` ${WORDED}` : '';
    return `Санкция прочитана программой из базы законов.${worded} Редакция и источник — ниже.`;
  }
  return null;
}

// An address runs to whitespace or a quote; punctuation that closes the sentence is not part of it.
const ADDRESS = /https?:\/\/[^\s<>"«»]+/g;
const TRAILING = /[.,;:!?)\]]+$/;

export function linkSegments(text: string): TextSegment[] {
  const segments: TextSegment[] = [];
  let plain = '';
  let last = 0;
  for (const match of text.matchAll(ADDRESS)) {
    const address = match[0].replace(TRAILING, '');
    if (!/^https?:\/\/[^/]/.test(address)) continue;
    plain += text.slice(last, match.index);
    if (plain) segments.push({text: plain});
    plain = '';
    segments.push({text: address, href: address});
    last = match.index + address.length;
  }
  plain += text.slice(last);
  if (plain) segments.push({text: plain});
  return segments;
}
