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
}

export interface BreakthroughRequest {
  refrigerant: string;
  zeolite: string;
  mass_flow: number;
  bed_height: number;
  column_diameter: number;
  threshold: number;
}

export interface BreakthroughResponse {
  request: BreakthroughRequest;
  equilibrium: Record<string, number>;
  diffusion: Record<string, number>;
  hydraulics: Record<string, number>;
  film: Record<string, number>;
  rosen: Record<string, number>;
  t_stoich: number;
  t_breakthrough: number;
  curve: { t: number[]; c: number[] };
}

export interface MatrixCell {
  zeolite: string;
  refrigerant: string;
  t_breakthrough: number | null;
  Ka: number | null;
}

export interface MatrixResponse {
  zeolites: string[];
  refrigerants: string[];
  cells: MatrixCell[];
}
