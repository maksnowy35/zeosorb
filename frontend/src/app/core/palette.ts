/** One colour per refrigerant, used on every page so a refrigerant is recognisable everywhere. */
export const REFRIGERANT_COLORS: Record<string, string> = {
  R32: '#2f7fa8',
  R22: '#5c8f4e',
  R134a: '#7a5ea8',
  R143a: '#c27c2c',
  R125: '#a23e5e',
  R152a: '#3d8f8c',
};

export const INK = '#1d2a33';
export const STEEL = '#5b6b76';
export const FROST = '#2f7fa8';
export const OCHRE = '#c8a24a';
export const SIGNAL = '#b4452f';

export function refColor(key: string): string {
  return REFRIGERANT_COLORS[key] ?? STEEL;
}

export function withAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
