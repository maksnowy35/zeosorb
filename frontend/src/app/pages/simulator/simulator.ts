import { KeyValuePipe } from '@angular/common';
import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { catchError, debounceTime, map, of, startWith, switchMap } from 'rxjs';

import { Api } from '../../core/api';
import { downloadCsv, duration, eventValue, formula, num, pct } from '../../core/format';
import {
  AuditRow, BreakthroughRequest, BreakthroughResponse, Mode, Model, SweepParameter, SweepResponse,
} from '../../core/models';
import { INK, refColor, SIGNAL, STEEL } from '../../core/palette';
import { LineChart, Marker, Series } from '../../shared/line-chart';
import { ColumnView } from './column-view';

type Result<T> = { state: 'loading' } | { state: 'ok'; data: T } | { state: 'error'; message: string };


const SWEEPS: Record<SweepParameter, { label: string; unit: string; start: number; stop: number }> = {
  mass_flow: { label: 'Mass flow', unit: 'kg/h', start: 5, stop: 200 },
  bed_height: { label: 'Bed height', unit: 'm', start: 0.5, stop: 5 },
  column_diameter: { label: 'Column diameter', unit: 'm', start: 0.2, stop: 1.0 },
  tortuosity: { label: 'Tortuosity', unit: '-', start: 1, stop: 6 },
  threshold: { label: 'Breakthrough criterion', unit: 'c/c₀', start: 0.01, stop: 0.3 },
};

function errorMessage(err: { error?: { detail?: unknown }; status?: number }): string {
  if (err.status === 0) return 'The API is not reachable. Start the backend: uvicorn app.main:app --reload';
  const d = err.error?.detail;
  return typeof d === 'string' ? d : 'The request was rejected by the API.';
}

@Component({
  selector: 'app-simulator',
  imports: [LineChart, ColumnView, KeyValuePipe, RouterLink],
  templateUrl: './simulator.html',
  styleUrl: './simulator.scss',
})
export class Simulator {
  private api = inject(Api);
  private route = inject(ActivatedRoute);

  readonly duration = duration;
  readonly formula = formula;
  readonly num = num;
  readonly pct = pct;
  readonly refColor = refColor;
  readonly sweeps = SWEEPS;
  readonly sweepKeys = Object.keys(SWEEPS) as SweepParameter[];
  /** keyvalue pipe sorts by key by default - keep the order from the data files */
  readonly keep = () => 0;

  materials = toSignal(this.api.materials$);

  // inputs
  refrigerant = signal('R22');
  zeolite = signal('4A');
  massFlow = signal(30);
  bedHeight = signal(2.89);
  columnDiameter = signal(0.5);
  thresholdPct = signal(5);
  /** null follows the default of the mode, a number is a value set with the slider */
  tortuosity = signal<number | null>(null);
  mode = signal<Mode>('corrected');
  model = signal<Model>('both');
  sweepParam = signal<SweepParameter>('mass_flow');

  /** frame of the bed animation, shared by the column drawing and the chart cursor */
  frame = signal(0);

  request = computed<BreakthroughRequest>(() => ({
    refrigerant: this.refrigerant(),
    zeolite: this.zeolite(),
    mass_flow: this.massFlow(),
    bed_height: this.bedHeight(),
    column_diameter: this.columnDiameter(),
    threshold: this.thresholdPct() / 100,
    tortuosity: this.tortuosity(),
    mode: this.mode(),
    model: this.model(),
  }));

  result = toSignal(
    toObservable(this.request).pipe(
      debounceTime(200),
      switchMap(req =>
        this.api.breakthrough(req).pipe(
          map(data => ({ state: 'ok', data }) as Result<BreakthroughResponse>),
          catchError(err => of({ state: 'error', message: errorMessage(err) } as Result<BreakthroughResponse>)),
          startWith({ state: 'loading' } as Result<BreakthroughResponse>),
        ),
      ),
    ),
    { initialValue: { state: 'loading' } as Result<BreakthroughResponse> },
  );

  /** last good response - keeps the page steady while the next one is loading */
  private lastData = signal<BreakthroughResponse | null>(null);
  data = computed(() => {
    const r = this.result();
    return r.state === 'ok' ? r.data : this.lastData();
  });
  loading = computed(() => this.result().state === 'loading');
  error = computed(() => {
    const r = this.result();
    return r.state === 'error' ? r.message : null;
  });

  sweep = toSignal(
    toObservable(computed(() => ({ req: this.request(), p: this.sweepParam() }))).pipe(
      debounceTime(300),
      switchMap(({ req, p }) =>
        this.api.sweep({ ...req, parameter: p, start: SWEEPS[p].start, stop: SWEEPS[p].stop, n: 30 }).pipe(
          catchError(() => of(null as SweepResponse | null)),
        ),
      ),
    ),
  );

  available = computed(() => {
    const m = this.materials();
    if (!m) return {} as Record<string, boolean>;
    const out: Record<string, boolean> = {};
    for (const z of Object.keys(m.zeolites)) {
      out[z] = m.adsorption[z]?.[this.refrigerant()] !== undefined;
    }
    return out;
  });

  // ---- chart data ----------------------------------------------------------------

  series = computed<Series[]>(() => {
    const d = this.data();
    if (!d) return [];
    const color = refColor(d.request.refrigerant);
    const out: Series[] = [];
    if (d.curves.rosen) {
      out.push({ label: 'Rosen (analytical)', x: d.curves.rosen.t.map(t => t / 3600), y: d.curves.rosen.c, color });
    }
    if (d.curves.ldf) {
      out.push({
        label: 'LDF + axial dispersion (numerical)',
        x: d.curves.ldf.t.map(t => t / 3600), y: d.curves.ldf.c, color: INK, dash: [6, 4], width: 1.6,
      });
    }
    return out;
  });

  markers = computed<Marker[]>(() => {
    const d = this.data();
    if (!d) return [];
    const thr = d.request.threshold;
    const t = d.t_breakthrough.rosen ?? d.t_breakthrough.ldf;
    return [
      { y: thr, label: `c/c₀ = ${pct(thr, thr < 0.1 ? 1 : 0)}`, color: STEEL },
      { x: t / 3600, label: duration(t), color: SIGNAL },
    ];
  });

  cursor = computed(() => {
    const p = this.data()?.profiles;
    if (!p) return null;
    return (p.t[Math.min(this.frame(), p.t.length - 1)] ?? 0) / 3600;
  });

  sweepSeries = computed<Series[]>(() => {
    const s = this.sweep();
    if (!s) return [];
    const color = refColor(this.refrigerant());
    return [
      { label: `breakthrough at ${this.thresholdPct()} %`, x: s.x, y: s.t_breakthrough.map(t => t / 3600), color },
      { label: 'stoichiometric (50 %)', x: s.x, y: s.t_stoich.map(t => t / 3600), color: STEEL, dash: [4, 4], width: 1.4 },
    ];
  });

  /** tortuosity actually used by the last calculation */
  tau = computed(() => this.tortuosity() ?? this.data()?.diffusion['tau'] ?? 1);

  sweepMarker = computed<Marker[]>(() => {
    const current: Record<SweepParameter, number> = {
      mass_flow: this.massFlow(),
      bed_height: this.bedHeight(),
      column_diameter: this.columnDiameter(),
      tortuosity: this.tau(),
      threshold: this.thresholdPct() / 100,
    };
    return [{ x: current[this.sweepParam()], label: 'current', color: SIGNAL }];
  });

  /** audit rows from the API grouped as they come (Equilibrium, Bed, Diffusion, ...) */
  auditGroups = computed<{ group: string; rows: AuditRow[] }[]>(() => {
    const groups: { group: string; rows: AuditRow[] }[] = [];
    for (const row of this.data()?.audit ?? []) {
      const last = groups[groups.length - 1];
      if (last?.group === row.group) last.rows.push(row);
      else groups.push({ group: row.group, rows: [row] });
    }
    return groups;
  });

  value(v: number | null, unit: string): string {
    return unit === 's' ? duration(v) : num(v);
  }

  /** corrected / thesis, only where the two differ noticeably */
  ratio(row: AuditRow): string {
    if (row.thesis === null || row.corrected === null || row.thesis === 0) return '';
    const r = row.corrected / row.thesis;
    if (Math.abs(r - 1) < 0.01) return '';
    return r >= 0.1 && r < 100 ? `×${r.toPrecision(2)}` : `×${num(r, 2)}`;
  }

  constructor() {
    const q = this.route.snapshot.queryParamMap;
    if (q.get('refrigerant')) this.refrigerant.set(q.get('refrigerant')!);
    if (q.get('zeolite')) this.zeolite.set(q.get('zeolite')!);
    if (q.get('mode') === 'thesis') this.mode.set('thesis');

    // jump the bed animation to the breakthrough moment whenever new results arrive
    effect(() => {
      const r = this.result();
      if (r.state !== 'ok') return;
      untracked(() => {
        this.lastData.set(r.data);
        const p = r.data.profiles;
        if (!p) return;
        const target = r.data.t_breakthrough.ldf ?? r.data.t_breakthrough.rosen;
        const idx = p.t.findIndex(t => t >= target);
        this.frame.set(idx < 0 ? p.t.length - 1 : idx);
      });
    });
  }

  selectRefrigerant(key: string): void {
    this.refrigerant.set(key);
    const m = this.materials();
    if (m && m.adsorption[this.zeolite()]?.[key] === undefined) {
      const z = Object.keys(m.zeolites).find(z => m.adsorption[z]?.[key] !== undefined);
      if (z) this.zeolite.set(z);
    }
  }

  setMode(m: Mode): void {
    this.mode.set(m);
    this.tortuosity.set(null);   // each mode has its own default
  }

  set(sig: { set(v: number): void }, e: Event): void {
    sig.set(eventValue(e));
  }

  exportCsv(): void {
    const d = this.data();
    if (!d) return;
    const rows: (number | null)[][] = [];
    const rosen = d.curves.rosen;
    const ldf = d.curves.ldf;
    if (rosen) rosen.t.forEach((t, i) => rows.push([t, rosen.c[i], null]));
    if (ldf) ldf.t.forEach((t, i) => rows.push([t, null, ldf.c[i]]));
    rows.sort((a, b) => (a[0] as number) - (b[0] as number));
    downloadCsv(`breakthrough_${d.request.refrigerant}_${d.request.zeolite}.csv`, ['t_s', 'c_rosen', 'c_ldf'], rows);
  }
}
