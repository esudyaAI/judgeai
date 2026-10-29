/**
 * Formats a term in months the way the design shows it:
 *   14 -> "1 г. 2 мес.", 12 -> "1 г.", 11 -> "11 мес.", 0 -> "0 мес."
 * Abbreviated forms avoid Russian plural agreement (год/года/лет).
 */
export function formatMonths(months: number): string {
  if (!Number.isInteger(months)) return `${Number(months.toFixed(6)).toString().replace('.', ',')} мес.`;
  const m = Math.max(0, months);
  const years = Math.floor(m / 12);
  const rest = m % 12;
  if (!years) return `${rest} мес.`;
  return rest ? `${years} г. ${rest} мес.` : `${years} г.`;
}

/** Position of a term on a 0..max scale, in percent (clamped). */
export function pctOf(months: number, maxMonths: number): number {
  if (maxMonths <= 0) return 0;
  return Math.min(100, Math.max(0, (months / maxMonths) * 100));
}

/** Russian plural: plural(4, ['файл', 'файла', 'файлов']) -> 'файла'. */
export function plural(n: number, forms: [string, string, string]): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];
  return forms[2];
}
