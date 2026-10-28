import type { CaseFile } from '../api/types';

type ReadingStatus = CaseFile['recognition'];

export function fileReadingLabel(file: Pick<CaseFile, 'pages' | 'recognition'>): string {
  const labels: Record<ReadingStatus, string> = {
    pending: 'Загружен · ожидает чтения',
    ok: 'Текст прочитан',
    partial: 'Прочитан частично',
    empty: 'Текст не найден',
    error: 'Ошибка чтения',
    unsupported: 'Формат не поддерживается',
  };
  const label = labels[file.recognition];
  return file.pages ? `${file.pages} стр. · ${label}` : label;
}

export function fileReadingWarning(status: ReadingStatus): string | null {
  switch (status) {
    case 'partial': return 'Текст прочитан не полностью. Проверьте предупреждения о чтении, прежде чем опираться на анализ.';
    case 'empty': return 'Читаемый текст не найден. Для скана нужно распознавание (OCR) — загрузите копию с текстовым слоем.';
    case 'error': return 'Файл не удалось прочитать. Проверьте кодировку или загрузите другую копию.';
    case 'unsupported': return 'Этот вариант файла не поддерживается. Сохраните его в поддерживаемом формате.';
    default: return null;
  }
}
