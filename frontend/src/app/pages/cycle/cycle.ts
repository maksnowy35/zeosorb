import { KeyValuePipe } from '@angular/common';
import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';

import { Api } from '../../core/api';
import { eventValue, num, pct } from '../../core/format';
import { INK, MODE_COLORS, OCHRE, refColor, SIGNAL, STEEL, withAlpha } from '../../core/palette';
import { CycleMode, CycleRequest, CycleResponse, ProcessDefaults, StepIn } from '../../core/process-models';
import { ProcessState } from '../../core/process-state';
import { Band, LineChart, Marker, Series } from '../../shared/line-chart';
import { CycleTimeline, MODE_LABEL } from './cycle-timeline';

const FEEDS = ['R410A', 'R407C', 'R404A', 'R507A', 'R32', 'R125', 'R134a', 'R143a', 'R152a', 'R22'];
const MODES: CycleMode[] = ['fill', 'adsorb', 'blowdown', 'evacuate', 'purge', 'idle'];
const BLUE_2 = '#3d86c0';

function message(err: { status?: number; error?: { detail?: unknown } }): string {
  if (err.status === 0) return 'The API is not reachable. Start the backend: uvicorn app.main:app --reload';
  const d = err.error?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return `Check the inputs: ${d[0].msg} (${(d[0].loc ?? []).slice(1).join(' ')})`;
  return 'The request was rejected by the API.';
}

@Component({
  selector: 'app-cycle',
  imports: [LineChart, CycleTimeline, KeyValuePipe],
  templateUrl: './cycle.html',
  styleUrl: './cycle.scss',
})
export class Cycle {
  private api = inject(Api);
  readonly shared = inject(ProcessState);

  readonly feeds = FEEDS;
  readonly modes = MODES;
  readonly modeLabel = MODE_LABEL;
  readonly modeColors = MODE_COLORS;
  readonly num = num;
  readonly pct = pct;
  readonly refColor = refColor;
  readonly zeolites = ['4A', '5A', '13X'];

  defaults = toSignal(this.api.processDefaults$);
  req = signal<CycleRequest | null>(null);
  preset = signal('two_bed_10_step');
  result = signal<CycleResponse | null>(null);
  running = signal(false);
  stale = signal(false);
  error = signal<string | null>(null);
  selected = signal<number | null>(null);
  view = signal<'A' | 'B'>('A');
  elapsed = signal(0);
  private timer?: ReturnType<typeof setInterval>;

  constructor() {
    effect(() => {
      const d = this.defaults();
      if (!d || untracked(this.req)) return;
      untracked(() => {
        this.req.set({
          bed: structuredClone(d.cycle.bed),
          plant: structuredClone(d.cycle.plant),
          steps: structuredClone(d.presets['two_bed_10_step'].steps),
          semantics: 'controller',
          max_cycles: 14,
        });
        this.run();
      });
    });
  }

  presetList = computed(() => {
    const d = this.defaults();
    return d ? Object.entries(d.presets).map(([key, p]) => ({ key, label: p.label, description: p.description })) : [];
  });

  presetDescription = computed(() => this.presetList().find(p => p.key === this.preset())?.description ?? '');

  bedPresets = computed(() => {
    const d: ProcessDefaults | undefined = this.defaults();
    return d ? Object.entries(d.bed_presets).map(([key, p]) => ({ key, ...p })) : [];
  });

  // ---- editing -----------------------------------------------------------------------------

  patch(fn: (r: CycleRequest) => void): void {
    const cur = this.req();
    if (!cur) return;
    const next = structuredClone(cur);
    fn(next);
    this.req.set(next);
    if (this.result()) this.stale.set(true);
  }

  setPath(path: string, value: unknown): void {
    this.patch(r => {
      const keys = path.split('.');
      let o: Record<string, unknown> = r as unknown as Record<string, unknown>;
      for (const k of keys.slice(0, -1)) o = o[k] as Record<string, unknown>;
      o[keys[keys.length - 1]] = value;
    });
  }

  setVal(path: string, e: Event): void {
    const v = eventValue(e);
    if (isFinite(v)) this.setPath(path, v);
  }

  setText(path: string, e: Event): void {
    this.setPath(path, (e.target as HTMLInputElement).value);
  }

  setFeed(f: string): void {
    this.patch(r => {
      r.plant.feed = f;
      r.plant.feed_composition = null;
      r.plant.purge_gas = null;
    });
  }

  setJacket(mode: CycleMode, e: Event): void {
    const raw = (e.target as HTMLInputElement).value;
    this.patch(r => (r.plant.jacket_C[mode] = raw === '' ? null : Number(raw)));
  }

  setRegenJacket(e: Event): void {
    const v = eventValue(e);
    this.patch(r => (['blowdown', 'evacuate', 'purge'] as CycleMode[]).forEach(m => (r.plant.jacket_C[m] = v)));
  }

  setLoadJacket(e: Event): void {
    const v = eventValue(e);
    this.patch(r => (['fill', 'adsorb'] as CycleMode[]).forEach(m => (r.plant.jacket_C[m] = v)));
  }

  usePreset(key: string): void {
    const d = this.defaults();
    if (!d) return;
    this.preset.set(key);
    this.patch(r => (r.steps = structuredClone(d.presets[key].steps)));
    this.selected.set(null);
  }

  useBed(key: string): void {
    const p = this.defaults()?.bed_presets[key];
    if (p) this.patch(r => { r.bed.diameter_m = p.diameter_m; r.bed.height_m = p.height_m; });
  }

  useFeedLine(): void {
    const f = this.shared.feed();
    if (!f) return;
    this.patch(r => {
      r.plant.feed = f.fluid;
      r.plant.feed_T_C = Math.round(f.outlet_C);
      r.plant.feed_barg = Math.round(f.reducer_barg * 100) / 100;
      r.plant.feed_composition = Object.keys(f.composition).length > 1 ? f.composition : null;
      r.plant.purge_gas = null;
    });
  }

  setStep(i: number, field: keyof StepIn, e: Event): void {
    const el = e.target as HTMLInputElement | HTMLSelectElement;
    const raw = el.value;
    this.patch(r => {
      const s = r.steps[i] as unknown as Record<string, unknown>;
      if (field === 'duration' || field === 'setpoint' || field === 'purge_pressure') {
        s[field] = raw === '' ? null : Number(raw);
      } else if (field === 'control') {
        s[field] = raw === '' ? null : raw;
      } else {
        s[field] = raw;
      }
    });
  }

  addStep(): void {
    this.patch(r => r.steps.push({
      name: `Step ${r.steps.length + 1}`, label: '', duration: 600, bed_a: 'idle', bed_b: 'idle',
      control: null, direction: '>', setpoint: null, purge_pressure: null,
    }));
  }

  removeStep(i: number): void {
    this.patch(r => r.steps.splice(i, 1));
  }

  // ---- running -------------------------------------------------------------------------------

  run(): void {
    const r = this.req();
    if (!r || this.running()) return;
    this.running.set(true);
    this.error.set(null);
    this.elapsed.set(0);
    const t0 = Date.now();
    this.timer = setInterval(() => this.elapsed.set(Math.round((Date.now() - t0) / 1000)), 1000);
    this.api.cycle(r).subscribe({
      next: res => {
        this.result.set(res);
        this.stale.set(false);
        this.running.set(false);
        clearInterval(this.timer);
        const sel = this.selected();
        if (sel !== null && sel > res.steps.length) this.selected.set(null);
      },
      error: err => {
        this.error.set(message(err));
        this.running.set(false);
        clearInterval(this.timer);
      },
    });
  }

  select(i: number): void {
    this.selected.set(this.selected() === i ? null : i);
  }

  // ---- derived for display ---------------------------------------------------------------------

  feedName = computed(() => {
    const r = this.req();
    if (!r) return '';
    return r.plant.feed_composition ? `${r.plant.feed} (as drawn off the tank)` : r.plant.feed;
  });

  headline = computed(() => {
    const res = this.result();
    if (!res) return '';
    const k = res.kpi;
    if (res.components.length > 1 && k.product_purity != null && k.extract_purity != null) {
      return `The unit takes ${num(k.feed_rate_kg_h)} kg/h and returns ${k.weak} at ${pct(k.product_purity)} purity ` +
        `and ${k.strong} at ${pct(k.extract_purity)}`;
    }
    return `The unit takes ${num(k.feed_rate_kg_h)} kg/h of ${res.components[0]} through a ${num(k.cycle_time_h)} h cycle`;
  });

  t = computed(() => (this.result()?.series.t ?? []).map(v => v / 3600));

  stepBands = computed<Band[]>(() => {
    const res = this.result();
    const sel = this.selected();
    if (!res || sel === null) return [];
    const s = res.steps[sel - 1];
    return s ? [{ from: s.t_start / 3600, to: (s.t_start + s.duration) / 3600, color: withAlpha(INK, 0.07) }] : [];
  });

  boundaries = computed<Marker[]>(() =>
    (this.result()?.steps ?? []).slice(1).map(s => ({ x: s.t_start / 3600, color: withAlpha(STEEL, 0.35) })));

  pressureSeries = computed<Series[]>(() => {
    const res = this.result();
    if (!res) return [];
    const t = this.t();
    const xs: number[] = [];
    const ys: (number | null)[] = [];
    for (const s of res.steps) {
      if (s.control_bed && s.setpoint_barg !== null && s.duration > 0) {
        xs.push(s.t_start / 3600, (s.t_start + s.duration) / 3600, (s.t_start + s.duration) / 3600);
        ys.push(s.setpoint_barg, s.setpoint_barg, null);
      }
    }
    return [
      { label: 'bed A', x: t, y: res.series.A.P, color: INK, width: 2 },
      { label: 'bed B', x: t, y: res.series.B.P, color: BLUE_2, width: 1.6 },
      { label: 'step setpoint', x: xs, y: ys, color: SIGNAL, dash: [5, 3], width: 1.4 },
    ];
  });

  pressureMarkers = computed<Marker[]>(() => {
    const r = this.req();
    const m = [...this.boundaries()];
    if (r) m.push({ y: r.plant.vacuum_barg, label: `vacuum source limit ${r.plant.vacuum_barg.toFixed(2)} bar g`, color: STEEL });
    return m;
  });

  temperatureSeries = computed<Series[]>(() => {
    const res = this.result();
    const r = this.req();
    if (!res || !r) return [];
    const b = res.series[this.view()];
    const t = this.t();
    const jx: number[] = [];
    const jy: (number | null)[] = [];
    for (const s of res.steps) {
      const j = s.beds[this.view()].jacket_T;
      jx.push(s.t_start / 3600, (s.t_start + s.duration) / 3600, (s.t_start + s.duration) / 3600);
      jy.push(j, j, null);
    }
    return [
      { label: 'top', x: t, y: b.T_top, color: SIGNAL, width: 1.6 },
      { label: 'middle', x: t, y: b.T_mid, color: INK, width: 2 },
      { label: 'bottom', x: t, y: b.T_bottom, color: BLUE_2, width: 1.6 },
      { label: 'jacket', x: jx, y: jy, color: OCHRE, dash: [2, 3], width: 1.6 },
    ];
  });

  loadingSeries = computed<Series[]>(() => {
    const res = this.result();
    if (!res) return [];
    const b = res.series[this.view()];
    return res.components.map(c => ({ label: c, x: this.t(), y: b.q_mean[c], color: refColor(c) }));
  });

  flowSeries = computed<Series[]>(() => {
    const res = this.result();
    if (!res) return [];
    const b = res.series[this.view()];
    const t = this.t();
    return [
      { label: 'feed in', x: t, y: b.flow_in_top, color: OCHRE, width: 1.8 },
      { label: 'product out', x: t, y: b.flow_out_bottom, color: INK, width: 1.8 },
      { label: 'to regenerate', x: t, y: b.flow_out_top, color: BLUE_2, width: 1.8 },
    ];
  });

  outletSeries = computed<Series[]>(() => {
    const res = this.result();
    if (!res || res.components.length < 2) return [];
    const b = res.series[this.view()];
    return res.components.map(c => ({ label: c, x: this.t(), y: b.y_bottom[c].map(v => v * 100), color: refColor(c) }));
  });

  profile = computed(() => {
    const res = this.result();
    const sel = this.selected() ?? res?.steps.length ?? null;
    if (!res || sel === null) return null;
    const p = res.profiles[sel - 1];
    if (!p) return null;
    const z = res.bed.z;
    return {
      step: res.steps[sel - 1],
      q: res.components.map((c, i) => ({ label: c, x: z, y: p.q.map(row => row[i]), color: refColor(c) })) as Series[],
      T: [{ label: 'bed', x: z, y: p.T, color: INK }] as Series[],
    };
  });

  stepRows = computed(() => {
    const res = this.result();
    if (!res) return [];
    const sum = (o: Record<string, number>) => Object.values(o).reduce((a, b) => a + b, 0);
    return res.steps.map(s => {
      const a = s.beds.A, b = s.beds.B;
      const prod = sum(a.product_kg) + sum(b.product_kg);
      const strong = res.kpi.strong;
      const strongShare = prod > 1e-6 ? ((a.product_kg[strong] ?? 0) + (b.product_kg[strong] ?? 0)) / prod : null;
      return {
        s, a, b,
        feed: sum(a.feed_kg) + sum(b.feed_kg),
        product: prod,
        strongShare,
        regen: sum(a.regen_kg) + sum(b.regen_kg),
        heat: a.heat_in_kWh + b.heat_in_kWh,
        flagged: res.findings.some(f => f.severity === 'warning' && (f.steps ?? []).includes(s.index)),
      };
    });
  });

  stepTime(s: { duration: number; planned: number; ended_by: string }): string {
    if (s.ended_by === 'immediate') return '0 s';
    return s.ended_by === 'setpoint' ? `${s.duration.toFixed(0)} of ${s.planned.toFixed(0)} s` : `${s.duration.toFixed(0)} s`;
  }

  endedBy(s: { ended_by: string; control_bed: string | null; t_reach: number | null }): string {
    if (s.ended_by === 'immediate') return 'ended at once';
    if (s.ended_by === 'setpoint') return 'setpoint';
    if (!s.control_bed) return 'time';
    return s.t_reach !== null ? `time, setpoint at ${s.t_reach.toFixed(0)} s` : 'time, setpoint missed';
  }

  isWarning(i: number): boolean {
    return this.stepRows()[i - 1]?.flagged ?? false;
  }
}
