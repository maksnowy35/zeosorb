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

const COLD = '#1a78bd';
const NEUTRAL = '#d9dedb';
const HOT = '#b4452f';

function mixHex(a: string, b: string, t: number): string {
  const pa = parseInt(a.slice(1), 16);
  const pb = parseInt(b.slice(1), 16);
  const ch = (s: number) => Math.round(((pa >> s) & 255) * (1 - t) + ((pb >> s) & 255) * t);
  return `rgb(${ch(16)}, ${ch(8)}, ${ch(0)})`;
}

/** Diverging temperature scale around the ambient temperature: blue below, red above, grey at ambient. */
export function tempColor(T: number, ambient = 20): string {
  if (T <= ambient) return mixHex(NEUTRAL, COLD, Math.min((ambient - T) / 60, 1));
  return mixHex(NEUTRAL, HOT, Math.min((T - ambient) / 150, 1));
}

/** Colours of the cycle modes: the loading side in ochre, the regenerating side in blue. */
export const MODE_COLORS: Record<string, string> = {
  fill: '#e2c98a',
  adsorb: '#b8902f',
  blowdown: '#9cc0dc',
  evacuate: '#3d86c0',
  purge: '#1d5784',
  idle: '#d9dedb',
};

export const MODE_TEXT: Record<string, string> = {
  fill: '#1d2a33',
  adsorb: '#1d2a33',
  blowdown: '#1d2a33',
  evacuate: '#ffffff',
  purge: '#ffffff',
  idle: '#5b6b76',
};
