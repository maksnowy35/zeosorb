/** "44 min", "2.4 h", "16 h" - whatever reads best for a breakthrough time. */
export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !isFinite(seconds)) return '–';
  if (seconds < 90) return `${seconds.toFixed(0)} s`;
  const min = seconds / 60;
  if (min < 90) return `${min.toFixed(0)} min`;
  const h = seconds / 3600;
  return h < 10 ? `${h.toFixed(1)} h` : `${h.toFixed(0)} h`;
}

/** Engineering-ish number formatting for tables. */
export function num(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !isFinite(v)) return '–';
  const a = Math.abs(v);
  if (a !== 0 && (a < 1e-2 || a >= 1e5)) {
    const [m, e] = v.toExponential(digits - 1).split('e');
    return `${m}·10${superscript(Number(e))}`;
  }
  return Number(v.toPrecision(digits)).toLocaleString('en-US', { maximumFractionDigits: 6 });
}

function superscript(n: number): string {
  const map: Record<string, string> = { '-': '⁻', '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹' };
  return String(n).split('').map(ch => map[ch] ?? ch).join('');
}

export function pct(v: number, digits = 0): string {
  return `${(v * 100).toFixed(digits)}\u00a0%`;
}

export function eventValue(e: Event): number {
  return Number((e.target as HTMLInputElement).value);
}

export function downloadCsv(filename: string, header: string[], rows: (number | string | null)[][]): void {
  const text = [header.join(','), ...rows.map(r => r.map(v => (v === null ? '' : v)).join(','))].join('\n');
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** "K_a", "Re^0.54" -> HTML with <sub>/<sup>, for symbols and short formulas in tables. */
export function formula(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/_([A-Za-z0-9]+(?:,[A-Za-z0-9]+)?)/g, '<sub>$1</sub>')
    .replace(/\^([0-9./]+)/g, '<sup>$1</sup>');
}
