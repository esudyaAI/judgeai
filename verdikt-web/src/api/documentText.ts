/** Bounded authenticated text transport, separate from preview presentation state. */
export async function loadDocumentText(url: string, signal: AbortSignal, maxBytes = 5 * 1024 * 1024): Promise<string> {
  let response: Response;
  try { response = await fetch(url, {credentials:'same-origin',signal}); }
  catch (cause) { if (signal.aborted) throw cause; throw new Error('Нет связи с сервером. Проверьте подключение и повторите попытку.'); }
  if (response.status === 401 && typeof window !== 'undefined') window.dispatchEvent(new Event('judgeai:unauthorized'));
  if (!response.ok) throw new Error('Не удалось загрузить текст. Проверьте доступ и повторите попытку.');
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Не удалось прочитать текст документа.');
  const chunks: Uint8Array[] = []; let bytes = 0;
  const limitError = new Error('Текст слишком большой для просмотра. Скачайте оригинал.');
  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maxBytes) { await reader.cancel(); throw limitError; }
      chunks.push(value);
    }
  } catch (cause) {
    if (signal.aborted || cause === limitError) throw cause;
    throw new Error('Не удалось прочитать текст документа. Повторите загрузку или скачайте оригинал.');
  } finally { reader.releaseLock(); }
  const buffer = new Uint8Array(bytes); let offset = 0;
  for (const chunk of chunks) { buffer.set(chunk, offset); offset += chunk.byteLength; }
  return new TextDecoder('utf-8').decode(buffer);
}
