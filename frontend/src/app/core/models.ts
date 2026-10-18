export type Mode = 'corrected' | 'thesis';
export type Model = 'rosen' | 'ldf' | 'both';
export type SweepParameter = 'mass_flow' | 'bed_height' | 'column_diameter' | 'tortuosity' | 'threshold';

export interface Refrigerant {
  key: string;
  name: string;
  formula: string;
  molar_mass: number;
  molecule_size: number;
  viscosity: number;
  gwp_ar4: number;
}

export interface Zeolite {
  key: string;
  name: string;
  grain_radius: number;
  pore_diameter: number;
  bed_porosity: number;
  bulk_density: number;
  channel_diameter: number;
  source: string;
}

export interface Materials {
  refrigerants: Record<string, Refrigerant>;
  zeolites: Record<string, Zeolite>;
  adsorption: Record<string, Record<string, number>>;
  blends: Record<string, Record<string, number>>;
}

export interface BedParams {
  mass_flow: number;
  bed_height: number;
  column_diameter: number;
  threshold: number;
  mode: Mode;
  tortuosity: number;
}

export interface BreakthroughRequest extends BedParams {
  refrigerant: string;
  zeolite: string;
  model: Model;
}

export interface Curve {
  t: number[];
  c: number[];
}

export interface Profiles {
  zeta: number[];
  t: number[];
  c: number[][];
  q: number[][];
}

export interface BreakthroughResponse {
  request: BreakthroughRequest;
  equilibrium: Record<string, number>;
  diffusion: Record<string, number>;
  hydraulics: Record<string, number>;
  film: Record<string, number>;
  film_correlation: string;
  rosen: Record<string, number>;
  dispersion: Record<string, number>;
  spreading: Record<string, number>;
  t_stoich: number;
  t_breakthrough: { rosen: number; ldf: number | null };
  curves: { rosen: Curve | null; ldf: Curve | null };
  profiles: Profiles | null;
  solver: { n_cells: number; n_rhs: number; runtime_ms: number; stanton: number; peclet: number; kappa: number } | null;
}

export interface MatrixCell {
  zeolite: string;
  refrigerant: string;
  t_breakthrough: number | null;
  t_stoich: number | null;
  Ka: number | null;
  lambda: number | null;
  sigma_rel: number | null;
}

export interface MatrixResponse {
  zeolites: string[];
  refrigerants: string[];
  cells: MatrixCell[];
}

export interface SeparationRequest extends BedParams {
  zeolite: string;
  refrigerant_a: string;
  refrigerant_b: string;
  fraction_a: number;
}

export interface SeparationOption {
  zeolite: string;
  weak: string;
  strong: string;
  alpha: number;
  t_weak_full: number;
  t_strong_break: number;
  window: number;
}

export interface SeparationResponse {
  request: SeparationRequest;
  result: SeparationOption;
  curves: Record<string, Curve>;
  ranking: SeparationOption[];
}

export interface SweepRequest extends BedParams {
  refrigerant: string;
  zeolite: string;
  parameter: SweepParameter;
  start: number;
  stop: number;
  n: number;
}

export interface SweepResponse {
  parameter: SweepParameter;
  x: number[];
  t_breakthrough: number[];
  t_stoich: number[];
  sigma_rel: number[];
}
