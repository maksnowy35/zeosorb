import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from './api.service';
import { BreakthroughResponse } from './models';

interface Row {
  group: keyof BreakthroughResponse;
  key: string;
  label: string;
  unit: string;
}

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App implements OnInit {
  private api = inject(ApiService);

  refrigerants = signal<string[]>([]);
  zeolites = signal<string[]>([]);
  result = signal<BreakthroughResponse | null>(null);
  error = signal<string | null>(null);
  loading = signal(false);

  refrigerant = 'R22';
  zeolite = '4A';
  massFlow = 30;
  threshold = 0.05;

  rows: Row[] = [
    { group: 'equilibrium', key: 'c_star', label: 'c* (gas density)', unit: 'kg/m3' },
    { group: 'equilibrium', key: 'q', label: 'adsorbed amount @ 0.8 bar', unit: 'mol/kg' },
    { group: 'equilibrium', key: 'av', label: 'av', unit: 'kg/m3' },
    { group: 'equilibrium', key: 'Ka', label: 'Henry constant Ka', unit: '-' },
    { group: 'diffusion', key: 'D', label: 'D (gas in gas)', unit: 'm2/s' },
    { group: 'diffusion', key: 'DK', label: 'DK (Knudsen)', unit: 'm2/s' },
    { group: 'diffusion', key: 'D_eff', label: "D' (effective)", unit: 'm2/s' },
    { group: 'hydraulics', key: 'w', label: 'w (velocity in bed channels)', unit: 'm/s' },
    { group: 'film', key: 'Re', label: 'Re', unit: '-' },
    { group: 'film', key: 'Sc', label: 'Sc', unit: '-' },
    { group: 'film', key: 'Sh', label: 'Sh', unit: '-' },
    { group: 'film', key: 'kcg', label: 'kc,g', unit: 'm/s' },
    { group: 'rosen', key: 'lambda', label: "lambda' (length parameter)", unit: '-' },
    { group: 'rosen', key: 'psi', label: 'psi (mass transfer resistance)', unit: '-' },
  ];

  ngOnInit(): void {
    this.api.materials().subscribe(m => {
      this.refrigerants.set(Object.keys(m.refrigerants));
      this.zeolites.set(Object.keys(m.zeolites));
    });
  }

  calculate(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.breakthrough({
      refrigerant: this.refrigerant,
      zeolite: this.zeolite,
      mass_flow: this.massFlow,
      bed_height: 2.89,
      column_diameter: 0.5,
      threshold: this.threshold,
    }).subscribe({
      next: res => {
        this.result.set(res);
        this.loading.set(false);
      },
      error: err => {
        this.result.set(null);
        this.error.set(err.error?.detail ?? 'Backend not responding (is uvicorn running on :8000?)');
        this.loading.set(false);
      },
    });
  }

  value(r: BreakthroughResponse, row: Row): number {
    return (r[row.group] as Record<string, number>)[row.key];
  }

  fmt(v: number | undefined): string {
    if (v === undefined) return '';
    const a = Math.abs(v);
    if (a !== 0 && (a < 0.01 || a >= 1e5)) return v.toExponential(3);
    return v.toFixed(3);
  }
}
