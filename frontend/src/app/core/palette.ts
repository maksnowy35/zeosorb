/**
 * One colour per refrigerant, used on every page so a refrigerant is recognisable everywhere.
 * Checked for colour-vision deficiency separation and contrast against the page background (#eef1ef).
 */
export const REFRIGERANT_COLORS: Record<string, string> = {
  R32: '#1a78bd',
  R22: '#4f9046',
  R134a: '#7c5cb0',
  R143a: '#b46c1a',
  R125: '#a8365c',
  R152a: '#0e9089',
};

export const INK = '#1d2a33';
export const STEEL = '#5b6b76';
export const FROST = '#1a78bd';
export const OCHRE = '#c8a24a';
export const SIGNAL = '#b4452f';

export function refColor(key: string): string {
  return REFRIGERANT_COLORS[key] ?? STEEL;
}

export function withAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
