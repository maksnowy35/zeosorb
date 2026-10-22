import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { catchError, debounceTime, filter, map, of, startWith, switchMap } from 'rxjs';

import { Api } from '../../core/api';
import { eventValue, num, pct } from '../../core/format';
import { INK, OCHRE, refColor, SIGNAL, STEEL, withAlpha } from '../../core/palette';
import { FeedRequest, FeedResponse, HeatingKind, SegmentIn } from '../../core/process-models';
import { ProcessState } from '../../core/process-state';
import { LineChart, Marker, Series } from '../../shared/line-chart';
import { LineSchematic } from './line-schematic';

type Result = { state: 'loading' } | { state: 'ok'; data: FeedResponse } | { state: 'error'; message: string };

const SINGLE = ['R32', 'R22', 'R134a', 'R143a', 'R125', 'R152a'];
const BLENDS = ['R410A', 'R407C', 'R404A', 'R507A'];

const HEATING_LABEL: Record<HeatingKind, string> = {
  medium: 'Water jacket',
  trace: 'Electric trace',
  insulated: 'Insulated',
  bare: 'Bare pipe',
};

function message(err: { status?: number; error?: { detail?: unknown } }): string {
  if (err.status === 0) return 'The API is not reachable. Start the backend: uvicorn app.main:app --reload';
  const d = err.error?.detail;
  return typeof d === 'string' ? d : 'The request was rejected by the API.';
}

@Component({
  selector: 'app-feed',
  imports: [LineChart, LineSchematic],
  templateUrl: './feed.html',
  styleUrl: './feed.scss',
})
export class Feed {
  private api = inject(Api);
  private shared = inject(ProcessState);

  readonly single = SINGLE;
  readonly blends = BLENDS;
  readonly heatingKinds = Object.keys(HEATING_LABEL) as HeatingKind[];
  readonly heatingLabel = HEATING_LABEL;
  readonly num = num;
  readonly pct = pct;
  readonly refColor = refColor;
  readonly zeolites = ['4A', '5A', '13X'];

  req = signal<FeedRequest | null>(null);
  solving = signal<number | null>(null);
  solveNote = signal<string | null>(null);

  private defaults = toSignal(this.api.processDefaults$);

  result = toSignal(
    toObservable(this.req).pipe(
      filter((r): r is FeedRequest => r !== null),
      debounceTime(350),
      switchMap(r => this.api.feed(r).pipe(
        map(data => ({ state: 'ok', data }) as Result),
        catchError(err => of({ state: 'error', message: message(err) } as Result)),
        startWith({ state: 'loading' } as Result),
      )),
    ),
    { initialValue: { state: 'loading' } as Result },
  );

  private last = signal<FeedResponse | null>(null);
  data = computed(() => {
    const r = this.result();
    return r.state === 'ok' ? r.data : this.last();
  });
  loading = computed(() => this.result().state === 'loading' || this.solving() !== null);
  error = computed(() => {
    const r = this.result();
    return r.state === 'error' ? r.message : null;
  });

  constructor() {
    effect(() => {
      const d = this.defaults();
      if (d && !untracked(this.req)) this.req.set(structuredClone(d.feed));
    });
    effect(() => {
      const r = this.result();
      if (r.state !== 'ok') return;
      untracked(() => {
        this.last.set(r.data);
        const req = this.req();
        if (req) {
          this.shared.feed.set({
            fluid: req.fluid, outlet_C: r.data.outlet.T_C, composition: r.data.composition,
            reducer_barg: req.reducer_bar - 1.01325, mass_flow: req.mass_flow,
          });
        }
      });
    });
  }

  // ---- editing ---------------------------------------------------------------------------

  patch(fn: (r: FeedRequest) => void): void {
    const cur = this.req();
    if (!cur) return;
    const next = structuredClone(cur);
    fn(next);
    this.solveNote.set(null);
    this.req.set(next);
  }

  /** Set a field by its dotted path, e.g. 'tank.volume_L'. */
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

  setSegVal(i: number, path: string, e: Event): void {
    const v = eventValue(e);
    if (isFinite(v)) this.setPath(`segments.${i}.${path}`, v);
  }

  setTankTemperature(e: Event): void {
    const v = eventValue(e);
    if (!isFinite(v)) return;
    this.patch(r => {
      r.tank.T0_C = v;
      r.tank.heater_T_C = v;
    });
  }

  setHeating(i: number, kind: HeatingKind): void {
    this.patch(r => {
      const h = r.segments[i].heating;
      h.kind = kind;
      if (kind === 'trace' && h.q_trace_W_m === 0) h.q_trace_W_m = 100;
    });
  }

  addSegment(): void {
    this.patch(r => r.segments.push({
      name: `Segment ${r.segments.length + 1}`, D_mm: 40, L_m: 2,
      heating: { kind: 'insulated', T_medium_C: 90, h_medium: 1000, q_trace_W_m: 0, insulation_mm: 30 },
    }));
  }

  removeSegment(i: number): void {
    this.patch(r => {
      r.segments.splice(i, 1);
      r.segments.forEach((s, k) => (s.name = `Segment ${k + 1}`));
    });
  }

  solve(i: number): void {
    const r = this.req();
    if (!r) return;
    this.solving.set(i);
    this.solveNote.set(null);
    this.api.feedSolve({ ...r, segment: i }).subscribe({
      next: res => {
        const s = res.solved!;
        const what = s.kind === 'medium' ? 'jacket' : 'trace';
        this.solveNote.set(s.reached
          ? `${r.segments[i].name}: a ${what} at ${s.value.toFixed(s.kind === 'medium' ? 1 : 0)} ${s.unit} brings the gas to ${r.target_C.toFixed(0)} °C.`
          : `${r.segments[i].name} cannot do it alone: at its limit (${s.value.toFixed(0)} ${s.unit}) the gas reaches ${res.outlet.T_C.toFixed(0)} °C.`);
        const note = this.solveNote();
        this.patch(x => {
          if (s.kind === 'medium') x.segments[i].heating.T_medium_C = Math.round(s.value * 10) / 10;
          else x.segments[i].heating.q_trace_W_m = Math.round(s.value);
        });
        this.solveNote.set(note);
        this.solving.set(null);
      },
      error: err => {
        this.solveNote.set(message(err));
        this.solving.set(null);
      },
    });
  }

  // ---- charts ----------------------------------------------------------------------------

  lineSeries = computed<Series[]>(() => {
    const d = this.data();
    if (!d) return [];
    const z = d.line.z;
    return [
      { label: 'gas', x: z, y: d.line.T_C, color: INK, width: 2.2 },
      { label: 'dew point', x: z, y: d.line.T_dew_C, color: STEEL, dash: [6, 4], width: 1.4 },
      { label: 'jacket / surroundings', x: z, y: d.line.T_outside_C, color: OCHRE, dash: [2, 3], width: 1.6, stepped: true },
    ];
  });

  lineMarkers = computed<Marker[]>(() => {
    const d = this.data();
    if (!d) return [];
    const m: Marker[] = d.segments.slice(0, -1).map(s => ({ x: s.z_end, color: STEEL }));
    m.push({ y: d.target_C, label: `target ${d.target_C.toFixed(0)} °C`, color: SIGNAL });
    return m;
  });

  lineRange = computed(() => {
    const d = this.data();
    if (!d) return { min: undefined, max: undefined };
    const all = [...d.line.T_C, ...d.line.T_dew_C, ...d.line.T_outside_C, d.target_C];
    const lo = Math.min(...all), hi = Math.max(...all);
    return { min: Math.floor((lo - 10) / 20) * 20, max: Math.ceil((hi + 10) / 20) * 20 };
  });

  tankPressure = computed<Series[]>(() => {
    const d = this.data();
    if (!d) return [];
    return [{ label: 'tank', x: d.tank.t_h, y: d.tank.p_bar, color: INK }];
  });

  tankMarkers = computed<Marker[]>(() => {
    const d = this.data();
    return d ? [{ y: d.tank.p_needed_bar, label: `reducer needs ${d.tank.p_needed_bar.toFixed(1)} bar`, color: SIGNAL }] : [];
  });

  campaignSeries = computed<Series[]>(() => {
    const d = this.data();
    if (!d) return [];
    return [
      { label: 'gas at the adsorber', x: d.campaign.t_h, y: d.campaign.outlet_C, color: INK },
      { label: 'tank', x: d.tank.t_h, y: d.tank.T_C, color: STEEL, dash: [5, 4], width: 1.5 },
    ];
  });

  composition = computed(() => {
    const d = this.data();
    if (!d) return null;
    const names = Object.keys(d.tank.feed_composition);
    if (names.length < 2) return null;
    return names.map(n => ({ label: n, x: d.tank.t_h, y: d.tank.feed_composition[n].map(v => v * 100), color: refColor(n) }));
  });

  capacitySeries = computed<Series[]>(() => {
    const c = this.data()?.capacity;
    if (!c) return [];
    const names = Object.keys(c.q_kg);
    const s: Series[] = [{ label: names.length > 1 ? 'all components' : names[0], x: c.T_C, y: c.total_kg, color: INK, width: 2.2 }];
    if (names.length > 1) {
      for (const n of names) s.push({ label: n, x: c.T_C, y: c.q_kg[n], color: refColor(n), width: 1.5 });
    }
    return s;
  });

  capacityBand = computed(() => {
    const c = this.data()?.capacity;
    if (!c) return null;
    return { from: c.T_C[0], to: c.min_safe_C, color: withAlpha(SIGNAL, 0.12) };
  });

  capacityMarkers = computed<Marker[]>(() => {
    const d = this.data();
    if (!d?.capacity) return [];
    return [
      { x: d.target_C, label: `target ${d.target_C.toFixed(0)} °C`, color: SIGNAL, place: 'bottom' },
      { x: d.outlet.T_C, label: `arrives at ${d.outlet.T_C.toFixed(0)} °C`, color: INK },
    ];
  });

  viscositySeries = computed<Series[]>(() => {
    const c = this.data()?.capacity;
    if (!c) return [];
    return [{ label: 'viscosity', x: c.T_C, y: c.mu_uPa_s, color: INK }];
  });

  // ---- headline ---------------------------------------------------------------------------

  headline = computed(() => {
    const d = this.data();
    if (!d) return '';
    const gap = d.outlet.T_C - d.target_C;
    const where = Math.abs(gap) <= 2 ? 'on target' : `${Math.abs(gap).toFixed(0)} K ${gap < 0 ? 'short of' : 'above'} ${d.target_C.toFixed(0)} °C`;
    return `${d.fluid} reaches the adsorber at ${d.outlet.T_C.toFixed(0)} °C, ${where}`;
  });

  totalDuty = computed(() => (this.data()?.segments ?? []).reduce((a, s) => a + s.duty_W, 0));

  duty(w: number): string {
    const a = Math.abs(w);
    const s = a >= 1000 ? `${(a / 1000).toFixed(2)} kW` : `${a.toFixed(0)} W`;
    return `${w >= 0 ? '+' : '−'}${s}`;
  }

  heatingValue(seg: SegmentIn): string {
    const h = seg.heating;
    return h.kind === 'medium' ? `${h.T_medium_C.toFixed(0)} °C` : h.kind === 'trace' ? `${h.q_trace_W_m.toFixed(0)} W/m` : '';
  }
}
