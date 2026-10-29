/** File admission rules shared by every attach path (dialog, drag&drop, clipboard paste). */
const ACCEPTED_EXTENSIONS = ['pdf', 'docx', 'dotx', 'txt', 'md'] as const;

/** `accept` attribute for <input type="file">. */
export const ACCEPT = ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`).join(',');

/** Same per-file cap as the backend admission policy (src/domain/uploads.py). */
export const MAX_FILE_BYTES = 50 * 1024 * 1024;

export interface FileRejection {
  name: string;
  reason: string;
}

export function validateFiles(files: File[]): { accepted: File[]; rejections: FileRejection[] } {
  const accepted: File[] = [];
  const rejections: FileRejection[] = [];
  const extensions: readonly string[] = ACCEPTED_EXTENSIONS;
  for (const file of files) {
    const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
    if (!extensions.includes(ext)) {
      rejections.push({ name: file.name, reason: 'формат не поддерживается, применим только PDF, DOCX, DOTX, TXT или MD' });
    } else if (file.size > MAX_FILE_BYTES) {
      rejections.push({ name: file.name, reason: `файл больше ${MAX_FILE_BYTES / 1024 / 1024} МБ` });
    } else {
      accepted.push(file);
    }
  }
  return { accepted, rejections };
}

/** Files copied in the OS file manager arrive via clipboardData.files, not as text. */
export function filesFromClipboard(data: DataTransfer | null): File[] {
  return data ? Array.from(data.files ?? []) : [];
}
