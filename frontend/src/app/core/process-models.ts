export type HeatingKind = 'medium' | 'trace' | 'insulated' | 'bare';
export type CycleMode = 'fill' | 'adsorb' | 'blowdown' | 'evacuate' | 'purge' | 'idle';

export interface HeatingIn {
  kind: HeatingKind;
  T_medium_C: number;
  h_medium: number;
  q_trace_W_m: number;
  insulation_mm: number;
}

export interface SegmentIn {
  name: string;
  D_mm: number;
  L_m: number;
  heating: HeatingIn;
}

export interface TankIn {
  volume_L: number;
  fill_kg: number;
  T0_C: number;
  T_amb_C: number;
  withdrawal: 'vapour' | 'liquid';
  heater: 'off' | 'thermostat' | 'power';
  heater_T_C: number;
  heater_kW: number;
}

export interface FeedRequest {
  fluid: string;
  mass_flow: number;
  reducer_bar: number;
  tank: TankIn;
  segments: SegmentIn[];
  target_C: number;
  superheat_min_K: number;
  campaign_h: number;
  zeolite: string;
}

export interface Finding {
  severity: 'warning' | 'info';
  text: string;
  steps?: number[];
}

export interface SegmentResult {
  name: string;
  z_start: number;
  z_end: number;
  T_in_C: number;
  T_out_C: number;
  x_in: number | null;
  x_out: number | null;
  duty_W: number;
  dp_Pa: number;
  residence_s: number;
  h_mean: number;
  ntu: number | null;
  re_in: number;
  re_out: number;
  u_in: number;
  u_out: number;
  wall_min_C: number;
  wall_max_C: number;
}

export interface FeedResponse {
  fluid: string;
  composition: Record<string, number>;
  reducer: { p_in_bar: number; p_out_bar: number; T_in_C: number; T_out_C: number; x_out: number | null; phase_out: string };
  line: {
    z: number[]; T_C: number[]; T_dew_C: number[]; p_bar: number[]; x: (number | null)[]; rho: number[];
    mu_uPa_s: number[]; u: number[]; re: number[]; h_in: number[]; q_W_m: number[]; T_wall_C: number[]; T_outside_C: number[];
  };
  segments: SegmentResult[];
  outlet: {
    T_C: number; p_bar: number; phase: string; x: number | null; dew_C: number; superheat_K: number;
    mu_uPa_s: number; rho: number; volume_flow_m3h: number;
  };
  tank: {
    t_h: number[]; T_C: number[]; p_bar: number[]; mass_kg: number[]; liquid_fraction: number[];
    q_heater_W: number[]; q_ambient_W: number[]; feed_composition: Record<string, number[]>;
    t_pressure_low: number | null; t_empty: number | null; hold_power_W: number; p_needed_bar: number;
  };
  campaign: {
    t_h: number[]; outlet_C: number[]; superheat_K: number[]; p_tank_bar: number[]; T_tank_C: number[];
    duty_W: number[]; feed_ok: boolean[];
  };
  capacity: {
    T_C: number[]; q_kg: Record<string, number[]>; total_kg: number[]; mu_uPa_s: number[]; dew_C: number; min_safe_C: number;
  } | null;
  target_C: number;
  superheat_min_K: number;
  warnings: string[];
  findings: Finding[];
  solved?: { segment: number; kind: string; reached: boolean; value: number; unit: string; bound_hit: boolean };
}

export interface StepIn {
  name: string;
  label: string;
  duration: number;
  bed_a: CycleMode;
  bed_b: CycleMode;
  control: 'A' | 'B' | null;
  direction: '>' | '<';
  setpoint: number | null;
  purge_pressure: number | null;
}

export interface CycleBedIn {
  zeolite: string;
  diameter_m: number;
  height_m: number;
  wall_mm: number;
  h_wall: number;
  k_bed: number;
  tortuosity: number | null;
  cells: number;
}

export interface CyclePlantIn {
  feed: string;
  feed_composition: Record<string, number> | null;
  feed_T_C: number;
  feed_barg: number;
  feed_flow: number;
  product_barg: number;
  product_flow: number;
  vacuum_speed: number;
  vacuum_barg: number;
  vacuum_max_flow: number;
  purge_gas: string | null;
  purge_flow: number;
  purge_T_C: number;
  purge_barg: number;
  jacket_C: Record<CycleMode, number | null>;
  T_amb_C: number;
}

export interface CycleRequest {
  bed: CycleBedIn;
  plant: CyclePlantIn;
  steps: StepIn[];
  semantics: 'controller' | 'transition';
  max_cycles: number;
}

export interface BedStepInfo {
  mode: CycleMode;
  P_start: number; P_end: number; P_min: number; P_max: number;
  T_start: number; T_end: number;
  q_start: number[]; q_end: number[];
  feed_kg: Record<string, number>; product_kg: Record<string, number>;
  regen_kg: Record<string, number>; purge_kg: Record<string, number>;
  heat_in_kWh: number; heat_out_kWh: number;
  jacket_T: number | null;
}

export interface CycleStepResult {
  index: number;
  name: string;
  label: string;
  t_start: number;
  duration: number;
  planned: number;
  ended_by: 'time' | 'setpoint' | 'immediate';
  control_bed: 'A' | 'B' | null;
  setpoint_barg: number | null;
  t_reach: number | null;
  beds: { A: BedStepInfo; B: BedStepInfo };
}

export interface BedSeries {
  P: number[]; T_top: number[]; T_mid: number[]; T_bottom: number[]; T_mean: number[]; heat: number[];
  q_mean: Record<string, number[]>; y_bottom: Record<string, number[]>; y_top: Record<string, number[]>;
  flow_in_top: number[]; flow_out_top: number[]; flow_out_bottom: number[];
}

export interface CycleResponse {
  components: string[];
  semantics: string;
  steps: CycleStepResult[];
  series: { t: number[]; A: BedSeries; B: BedSeries };
  profiles: { q: number[][]; T: number[] }[];
  kpi: {
    cycle_time_h: number; feed_kg: number; feed_rate_kg_h: number; product_kg: number; regen_kg: number; purge_kg: number;
    zeolite_kg: number; productivity: number; heat_in_kWh: number; heat_out_kWh: number; compressor_kWh: number;
    mass_balance_error: number; weak: string; strong: string; specific_energy_kWh_kg: number;
    product_purity?: number | null; product_recovery?: number | null; extract_purity?: number | null; extract_recovery?: number | null;
  };
  thermal: { U_jacket: number; tau_h: number; T_mean_min: number; T_mean_max: number; T_max: number };
  convergence: number[];
  css: boolean;
  cycles: number;
  bed: { volume_m3: number; zeolite_kg: number; cells: number; jacket_U: number; z: number[] };
  findings: Finding[];
}

export interface ProcessDefaults {
  feed: FeedRequest;
  cycle: { bed: CycleBedIn; plant: CyclePlantIn };
  presets: Record<string, { label: string; description: string; steps: StepIn[] }>;
  bed_presets: Record<string, { label: string; diameter_m: number; height_m: number }>;
  fluids: string[];
}
