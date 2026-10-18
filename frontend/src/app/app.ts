import { Component, OnInit, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

const API = 'http://localhost:8000';

interface Row {
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
  private http = inject(HttpClient);

  refrigerants = signal<string[]>([]);
  zeolites = signal<string[]>([]);
  result = signal<Record<string, number | string> | null>(null);
  error = signal<string | null>(null);
  loading = signal(false);

  refrigerant = 'R22';
  zeolite = '4A';
  massFlow = 30;
  threshold = 0.05;

  rows: Row[] = [
    { key: 'c_star', label: 'c* (gas density)', unit: 'kg/m3' },
    { key: 'q', label: 'adsorbed amount @ 0.8 bar', unit: 'mol/kg' },
    { key: 'av', label: 'av', unit: 'kg/m3' },
    { key: 'Ka', label: 'Henry constant Ka', unit: '-' },
    { key: 'D', label: 'D (gas in gas)', unit: 'm2/s' },
    { key: 'DK', label: 'DK (Knudsen)', unit: 'm2/s' },
    { key: 'D_eff', label: "D' (effective)", unit: 'm2/s' },
    { key: 'w', label: 'w (velocity in bed channels)', unit: 'm/s' },
    { key: 'Re', label: 'Re', unit: '-' },
    { key: 'Sc', label: 'Sc', unit: '-' },
    { key: 'Sh', label: 'Sh', unit: '-' },
    { key: 'kcg', label: 'kc,g', unit: 'm/s' },
    { key: 'lambda', label: "lambda' (length parameter)", unit: '-' },
    { key: 'psi', label: 'psi (mass transfer resistance)', unit: '-' },
    { key: 'E', label: 'E', unit: '-' },
  ];

  ngOnInit(): void {
    this.http.get<Record<string, unknown>>(`${API}/refrigerants`).subscribe(r => this.refrigerants.set(Object.keys(r)));
    this.http.get<Record<string, unknown>>(`${API}/zeolites`).subscribe(z => this.zeolites.set(Object.keys(z)));
  }

  calculate(): void {
    this.loading.set(true);
    this.error.set(null);
    this.http.post<Record<string, number | string>>(`${API}/calculate`, {
      refrigerant: this.refrigerant,
      zeolite: this.zeolite,
      mass_flow: this.massFlow,
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

  fmt(v: number | string | undefined): string {
    if (typeof v !== 'number') return String(v ?? '');
    const a = Math.abs(v);
    if (a !== 0 && (a < 0.01 || a >= 1e5)) return v.toExponential(3);
    return v.toFixed(3);
  }
}
