import { Component, computed, inject, signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { catchError, debounceTime, of, switchMap } from 'rxjs';

import { Api } from '../../core/api';
import { duration, eventValue, num, pct } from '../../core/format';
import { MatrixCell, MatrixResponse, Mode } from '../../core/models';
import { refColor } from '../../core/palette';

type Metric = 't_breakthrough' | 'Ka' | 'sigma_rel';

const METRICS: Record<Metric, { label: string; explain: string; log: boolean; higherIsBetter: boolean }> = {
  t_breakthrough: {
    label: 'Breakthrough time',
    explain: 'How long the bed holds the refrigerant back. Longer is better for removal.',
    log: true,
    higherIsBetter: true,
  },
  Ka: {
    label: 'Henry constant',
    explain: 'Adsorbed mass per bed volume over gas concentration. The ratio between two refrigerants is the selectivity proxy.',
    log: true,
    higherIsBetter: true,
  },
  sigma_rel: {
    label: 'Front width',
    explain: 'Spread of the breakthrough front relative to the stoichiometric time. Narrower fronts use the bed better.',
    log: false,
    higherIsBetter: false,
  },
};

const SCALE = ['#eef1ef', '#c9dde6', '#8fbcd2', '#2f7fa8', '#1d4f6b', '#1d2a33'];

function mix(a: string, b: string, t: number): string {
  const pa = parseInt(a.slice(1), 16);
  const pb = parseInt(b.slice(1), 16);
  const ch = (shift: number) => Math.round(((pa >> shift) & 255) * (1 - t) + ((pb >> shift) & 255) * t);
  return `rgb(${ch(16)}, ${ch(8)}, ${ch(0)})`;
}

function scaleColor(f: number): string {
  const x = Math.min(Math.max(f, 0), 1) * (SCALE.length - 1);
  const i = Math.min(Math.floor(x), SCALE.length - 2);
  return mix(SCALE[i], SCALE[i + 1], x - i);
}

@Component({
  selector: 'app-compare',
  templateUrl: './compare.html',
  styleUrl: './compare.scss',
})
export class Compare {
  private api = inject(Api);
  private router = inject(Router);

  readonly metrics = METRICS;
  readonly metricKeys = Object.keys(METRICS) as Metric[];
  readonly refColor = refColor;
  readonly duration = duration;

  massFlow = signal(30);
  thresholdPct = signal(5);
  mode = signal<Mode>('corrected');
  metric = signal<Metric>('t_breakthrough');

  materials = toSignal(this.api.materials$);

  matrix = toSignal(
    toObservable(computed(() => ({
      mass_flow: this.massFlow(),
      bed_height: 2.89,
      column_diameter: 0.5,
      threshold: this.thresholdPct() / 100,
      mode: this.mode(),
      tortuosity: 1,
    }))).pipe(
      debounceTime(200),
      switchMap(p => this.api.matrix(p).pipe(catchError(() => of(null as MatrixResponse | null)))),
    ),
  );

  private values = computed(() => {
    const m = this.matrix();
    const key = this.metric();
    return (m?.cells ?? []).map(c => c[key]).filter((v): v is number => v !== null);
  });

  ranked = computed(() => {
    const m = this.matrix();
    if (!m) return null;
    const key = this.metric();
    const cells = m.cells.filter(c => c[key] !== null).sort((a, b) => (b[key] as number) - (a[key] as number));
    const best = METRICS[key].higherIsBetter ? cells[0] : cells[cells.length - 1];
    const worst = METRICS[key].higherIsBetter ? cells[cells.length - 1] : cells[0];
    const perBed = m.zeolites.map(z => {
      const own = cells.filter(c => c.zeolite === z);
      return { zeolite: z, refrigerant: (METRICS[key].higherIsBetter ? own[0] : own[own.length - 1])?.refrigerant };
    });
    return { best, worst, perBed };
  });

  cell(z: string, r: string): MatrixCell | undefined {
    return this.matrix()?.cells.find(c => c.zeolite === z && c.refrigerant === r);
  }

  fraction(v: number): number {
    const vals = this.values();
    const meta = METRICS[this.metric()];
    const f = (x: number) => (meta.log ? Math.log(x) : x);
    const lo = f(Math.min(...vals));
    const hi = f(Math.max(...vals));
    return hi > lo ? (f(v) - lo) / (hi - lo) : 0.5;
  }

  background(v: number): string {
    return scaleColor(0.08 + 0.92 * this.fraction(v));
  }

  dark(v: number): boolean {
    return this.fraction(v) > 0.45;
  }

  format(c: MatrixCell): string {
    switch (this.metric()) {
      case 't_breakthrough':
        return duration(c.t_breakthrough);
      case 'Ka':
        return num(c.Ka);
      case 'sigma_rel':
        return `±${pct(c.sigma_rel ?? 0, 1)}`;
    }
  }

  open(c: MatrixCell): void {
    this.router.navigate(['/'], { queryParams: { refrigerant: c.refrigerant, zeolite: c.zeolite, mode: this.mode() } });
  }

  set(sig: { set(v: number): void }, e: Event): void {
    sig.set(eventValue(e));
  }
}
