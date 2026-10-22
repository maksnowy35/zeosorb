import { Component, ElementRef, OnDestroy, afterRenderEffect, input, untracked, viewChild } from '@angular/core';
import { Chart, ChartConfiguration, Plugin, registerables } from 'chart.js';

import { INK, SIGNAL, STEEL, withAlpha } from '../core/palette';

Chart.register(...registerables);
Chart.defaults.font.family = "'Barlow', system-ui, sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = STEEL;

export interface Series {
  label: string;
  x: number[];
  y: (number | null)[];      // null leaves a gap
  color: string;
  dash?: number[];
  width?: number;
  stepped?: boolean;
  fill?: boolean;            // shade the area under the line
}

export interface Marker {
  x?: number;
  y?: number;
  label?: string;
  color?: string;
  place?: 'top' | 'bottom';     // where the label of a vertical marker goes
}

export interface Band {
  from: number;
  to: number;
  label?: string;
  color: string;
}

interface Overlay {
  markers: Marker[];
  bands: Band[];
  cursor: number | null;
}

/** Draws reference lines, a shaded x-band and a moving cursor on top of the datasets. */
const overlayPlugin: Plugin = {
  id: 'zeosorbOverlay',
  beforeDatasetsDraw(chart) {
    const o = (chart as unknown as { $overlay?: Overlay }).$overlay;
    if (!o?.bands.length) return;
    const { ctx, chartArea: a, scales } = chart;
    ctx.save();
    for (const band of o.bands) {
      const x0 = Math.max(a.left, scales['x'].getPixelForValue(band.from));
      const x1 = Math.min(a.right, scales['x'].getPixelForValue(band.to));
      if (x1 <= x0) continue;
      ctx.fillStyle = band.color;
      ctx.fillRect(x0, a.top, x1 - x0, a.bottom - a.top);
      if (band.label) {
        ctx.fillStyle = INK;
        ctx.font = "500 12px 'Barlow', system-ui, sans-serif";
        ctx.textAlign = 'center';
        ctx.fillText(band.label, (x0 + x1) / 2, a.top + 16);
      }
    }
    ctx.restore();
  },
  afterDatasetsDraw(chart) {
    const o = (chart as unknown as { $overlay?: Overlay }).$overlay;
    if (!o) return;
    const { ctx, chartArea: a, scales } = chart;
    ctx.save();
    ctx.font = "12px 'Barlow', system-ui, sans-serif";
    for (const m of o.markers) {
      ctx.strokeStyle = m.color ?? STEEL;
      ctx.fillStyle = m.color ?? STEEL;
      ctx.lineWidth = 1;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      if (m.x !== undefined) {
        const px = scales['x'].getPixelForValue(m.x);
        if (px < a.left || px > a.right) continue;
        ctx.moveTo(px, a.top);
        ctx.lineTo(px, a.bottom);
        ctx.stroke();
        if (m.label) {
          ctx.textAlign = px > (a.left + a.right) / 2 ? 'right' : 'left';
          ctx.fillText(m.label, px + (ctx.textAlign === 'right' ? -6 : 6), m.place === 'bottom' ? a.bottom - 8 : a.top + 14);
        }
      } else if (m.y !== undefined) {
        const py = scales['y'].getPixelForValue(m.y);
        ctx.moveTo(a.left, py);
        ctx.lineTo(a.right, py);
        ctx.stroke();
        if (m.label) {
          ctx.textAlign = 'right';
          ctx.fillText(m.label, a.right - 4, py - 5);
        }
      }
    }
    if (o.cursor !== null) {
      const px = scales['x'].getPixelForValue(o.cursor);
      if (px >= a.left && px <= a.right) {
        ctx.setLineDash([]);
        ctx.strokeStyle = SIGNAL;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(px, a.top);
        ctx.lineTo(px, a.bottom);
        ctx.stroke();
      }
    }
    ctx.restore();
  },
};

@Component({
  selector: 'app-line-chart',
  template: `<div class="wrap" [style.height.px]="height()"><canvas #canvas [attr.aria-label]="ariaLabel()" role="img"></canvas></div>`,
  styles: `.wrap { position: relative; width: 100%; }`,
})
export class LineChart implements OnDestroy {
  series = input.required<Series[]>();
  xLabel = input('t [h]');
  yLabel = input('c / c₀');
  yMin = input<number | undefined>(0);
  yMax = input<number | undefined>(1);
  xMax = input<number | undefined>(undefined);
  markers = input<Marker[]>([]);
  band = input<Band | null>(null);
  bands = input<Band[]>([]);
  cursor = input<number | null>(null);
  height = input(320);
  ariaLabel = input('chart');
  legend = input(true);

  private canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private chart?: Chart;

  constructor() {
    // full rebuild when the data changes (after render, the canvas has to exist)
    afterRenderEffect(() => {
      const series = this.series();
      const xLabel = this.xLabel();
      const yLabel = this.yLabel();
      const yMin = this.yMin();
      const yMax = this.yMax();
      const xMax = this.xMax();
      const legend = this.legend();
      untracked(() => this.build(series, xLabel, yLabel, yMin, yMax, xMax, legend));
    });
    // cheap redraw for overlays (cursor moves every animation frame)
    afterRenderEffect(() => {
      const overlay: Overlay = { markers: this.markers(), bands: this.allBands(), cursor: this.cursor() };
      if (!this.chart) return;
      (this.chart as unknown as { $overlay: Overlay }).$overlay = overlay;
      this.chart.draw();
    });
  }

  private allBands(): Band[] {
    const b = this.band();
    return b ? [...this.bands(), b] : this.bands();
  }

  private build(series: Series[], xLabel: string, yLabel: string,
                yMin: number | undefined, yMax: number | undefined, xMax: number | undefined, legend: boolean): void {
    const datasets = series.map(s => ({
      label: s.label,
      data: s.x.map((x, i) => ({ x, y: s.y[i] })),
      borderColor: s.color,
      backgroundColor: withAlpha(s.color, 0.15),
      borderDash: s.dash ?? [],
      borderWidth: s.width ?? 2,
      pointRadius: 0,
      pointHoverRadius: 3,
      tension: 0,
      clip: 6,
      stepped: s.stepped ? ('before' as const) : false,
      fill: s.fill ? 'origin' : false,
      spanGaps: false,
    }));

    this.chart?.destroy();
    const config: ChartConfiguration = {
      type: 'line',
      data: { datasets },
      plugins: [overlayPlugin],
      options: {
        animation: false,
        maintainAspectRatio: false,
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
        scales: {
          x: {
            type: 'linear',
            max: xMax,
            title: { display: true, text: xLabel },
            grid: { color: 'rgba(29, 42, 51, 0.06)' },
          },
          y: {
            min: yMin,
            max: yMax,
            ticks: { maxTicksLimit: 7 },
            title: { display: true, text: yLabel },
            grid: { color: 'rgba(29, 42, 51, 0.06)' },
          },
        },
        plugins: {
          legend: { display: legend, position: 'bottom', labels: { boxWidth: 18, boxHeight: 2 } },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: ${Number(ctx.parsed.y).toPrecision(4)}`,
              title: items => `${xLabel.split(' [')[0]} = ${Number(items[0]?.parsed.x).toPrecision(3)}`,
            },
          },
        },
      },
    };
    const chart = new Chart(this.canvas().nativeElement, config);
    (chart as unknown as { $overlay: Overlay }).$overlay = {
      markers: untracked(this.markers),
      bands: untracked(() => this.allBands()),
      cursor: untracked(this.cursor),
    };
    chart.draw();
    this.chart = chart;
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }
}
