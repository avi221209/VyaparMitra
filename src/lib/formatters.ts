/**
 * Formatters adhering to VyaparMitra design standards.
 * All numbers use tabular-nums in UI rendering.
 */

export function formatINR(val: number, includeDecimals: boolean = false): string {
  if (val === undefined || val === null || isNaN(val)) return '₹ 0';
  const formatter = new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: includeDecimals ? 2 : 0,
    minimumFractionDigits: includeDecimals ? 2 : 0,
  });
  return `₹ ${formatter.format(val)}`;
}

export function formatCartons(val: number): string {
  if (val === undefined || val === null || isNaN(val)) return '0 cartons';
  const count = Math.round(val);
  const formatted = new Intl.NumberFormat('en-IN').format(count);
  return `${formatted} ${count === 1 ? 'carton' : 'cartons'}`;
}

export function formatDate(val: string | Date | undefined | null): string {
  if (!val) return '—';
  const d = typeof val === 'string' ? new Date(val) : val;
  if (isNaN(d.getTime())) return String(val);
  return d.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

export function formatDays(val: number): string {
  if (val === undefined || val === null || isNaN(val)) return '0 days';
  const count = Math.round(val);
  return `${count} ${count === 1 ? 'day' : 'days'}`;
}
