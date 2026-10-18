import { Component, ElementRef, OnDestroy, effect, input, viewChild } from '@angular/core';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

export interface CurveSeries {
  label: string;
  t: number[];   // s
  c: number[];   // c/c0
  color: string;
}

@Component({
  selector: 'app-breakthrough-chart',
  template: `<div class="wrap"><canvas #canvas></canvas></div>`,
  styles: `.wrap { position: relative; height: 340px; }`,
})
export class BreakthroughChart implements OnDestroy {
  series = input.required<CurveSeries[]>();
  threshold = input<number | null>(null);
  markerTime = input<number | null>(null);

  private canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private chart?: Chart;

  constructor() {
    effect(() => this.render());
  }

  private render(): void {
    const series = this.series();
    const thr = this.threshold();
    const marker = this.markerTime();

    const datasets: any[] = series.map(s => ({
      label: s.label,
      data: s.t.map((t, i) => ({ x: t / 3600, y: s.c[i] })),
      borderColor: s.color,
      backgroundColor: s.color,
      borderWidth: 2,
      pointRadius: 0,
      tension: 0,
    }));

    if (thr !== null && series.length) {
      const tMax = Math.max(...series.map(s => s.t[s.t.length - 1])) / 3600;
      datasets.push({
        label: `c/c0 = ${(thr * 100).toFixed(1)} %`,
        data: [{ x: 0, y: thr }, { x: tMax, y: thr }],
        borderColor: '#999',
        borderDash: [6, 4],
        borderWidth: 1,
        pointRadius: 0,
      });
    }
    if (marker !== null) {
      datasets.push({
        label: 'breakthrough',
        data: [{ x: marker / 3600, y: 0 }, { x: marker / 3600, y: 1 }],
        borderColor: '#d62728',
        borderWidth: 1,
        pointRadius: 0,
      });
    }

    this.chart?.destroy();
    this.chart = new Chart(this.canvas().nativeElement, {
      type: 'line',
      data: { datasets },
      options: {
        animation: false,
        maintainAspectRatio: false,
        scales: {
          x: { type: 'linear', title: { display: true, text: 't [h]' } },
          y: { min: 0, max: 1.05, title: { display: true, text: 'c / c0' } },
        },
        plugins: { legend: { position: 'bottom' } },
      },
    });
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }
}
