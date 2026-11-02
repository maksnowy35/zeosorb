import { Component, computed, inject, signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { catchError, debounceTime, map, of, switchMap } from 'rxjs';

import { Api } from '../../core/api';
import { duration, eventValue, num } from '../../core/format';
import { Mode, SeparationResponse } from '../../core/models';
import { OCHRE, refColor, SIGNAL, withAlpha } from '../../core/palette';
import { Band, LineChart, Marker, Series } from '../../shared/line-chart';

interface Preset {
  label: string;
  a: string;
  b: string;
  /** mass fraction of a in the pair */
  fraction: number;
  why: string;
}

const PRESETS: Preset[] = [
  { label: 'R410A', a: 'R32', b: 'R125', fraction: 0.5, why: '50/50 by mass, the most common recovered A/C refrigerant' },
  { label: 'R507A', a: 'R125', b: 'R143a', fraction: 0.5, why: 'azeotrope, cannot be split by distillation' },
  { label: 'R407C', a: 'R32', b: 'R134a', fraction: 0.31, why: 'its two main components, 23 % R32 and 52 % R134a' },
  { label: 'R404A', a: 'R125', b: 'R143a', fraction: 0.46, why: '44 % R125, 52 % R143a, 4 % R134a' },
  { label: 'R22 in R32', a: 'R22', b: 'R32', fraction: 0.1, why: 'removing 10 % of banned R22 from an R32 stream' },
];

type State = { ok: true; data: SeparationResponse } | { ok: false; message: string };

@Component({
  selector: 'app-separation',
  imports: [LineChart],
  templateUrl: './separation.html',
  styleUrl: './separation.scss',
})
export class Separation {
  private api = inject(Api);

  readonly presets = PRESETS;
  readonly duration = duration;
  readonly num = num;
  readonly refColor = refColor;
  readonly Math = Math;

  materials = toSignal(this.api.materials$);
  refrigerantKeys = computed(() => Object.keys(this.materials()?.refrigerants ?? {}));

  a = signal('R32');
  b = signal('R125');
  zeolite = signal('4A');
  massFlow = signal(30);
  bedHeight = signal(2.89);
  thresholdPct = signal(5);
  fractionPct = signal(50);
  mode = signal<Mode>('corrected');

  /** zeolites with isotherm data for both refrigerants */
  beds = computed(() => {
    const m = this.materials();
    if (!m) return [];
    return Object.keys(m.zeolites).map(z => ({
      key: z,
      ok: m.adsorption[z]?.[this.a()] !== undefined && m.adsorption[z]?.[this.b()] !== undefined,
    }));
  });

  state = toSignal(
    toObservable(computed(() => ({
      zeolite: this.zeolite(),
      refrigerant_a: this.a(),
      refrigerant_b: this.b(),
      fraction_a: this.fractionPct() / 100,
      mass_flow: this.massFlow(),
      bed_height: this.bedHeight(),
      column_diameter: 0.5,
      threshold: this.thresholdPct() / 100,
      mode: this.mode(),
      tortuosity: null,
    }))).pipe(
      debounceTime(200),
      switchMap(req => this.api.separation(req).pipe(
        map(data => ({ ok: true, data }) as State),
        catchError(err => of({ ok: false, message: err.error?.detail ?? 'The API is not reachable.' } as State)),
      )),
    ),
  );

  data = computed(() => {
    const s = this.state();
    return s?.ok ? s.data : null;
  });

  series = computed<Series[]>(() => {
    const d = this.data();
    if (!d) return [];
    return Object.entries(d.curves).map(([ref, c]) => ({
      label: ref,
      x: c.t.map(t => t / 3600),
      y: c.c,
      color: refColor(ref),
    }));
  });

  band = computed<Band | null>(() => {
    const r = this.data()?.result;
    if (!r || r.window <= 0) return null;
    return { from: r.t_weak_full / 3600, to: r.t_strong_break / 3600, color: withAlpha(OCHRE, 0.22), label: `only ${r.weak}` };
  });

  markers = computed<Marker[]>(() => {
    const r = this.data()?.result;
    if (!r) return [];
    return [
      { y: 0.95, label: 'weak one fully through (95 %)', color: refColor(r.weak) },
      { y: this.thresholdPct() / 100, label: `strong one breaks through (${this.thresholdPct()} %)`, color: refColor(r.strong) },
    ];
  });

  maxWindow = computed(() => Math.max(...(this.data()?.ranking ?? []).map(o => Math.abs(o.window)), 1));

  usePreset(p: Preset): void {
    this.a.set(p.a);
    this.b.set(p.b);
    this.fractionPct.set(Math.round(p.fraction * 100));
    this.pickBed();
  }

  setA(e: Event): void {
    this.a.set((e.target as HTMLSelectElement).value);
    this.pickBed();
  }

  setB(e: Event): void {
    this.b.set((e.target as HTMLSelectElement).value);
    this.pickBed();
  }

  /** keep the selected bed if it has data, otherwise jump to one that has */
  private pickBed(): void {
    const beds = this.beds();
    if (!beds.find(b => b.key === this.zeolite())?.ok) {
      const first = beds.find(b => b.ok);
      if (first) this.zeolite.set(first.key);
    }
  }

  isPreset(p: Preset): boolean {
    return p.a === this.a() && p.b === this.b() && Math.round(p.fraction * 100) === this.fractionPct();
  }

  set(sig: { set(v: number): void }, e: Event): void {
    sig.set(eventValue(e));
  }

  barColor(window: number): string {
    return window > 0 ? OCHRE : SIGNAL;
  }
}
