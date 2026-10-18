import { Component, OnDestroy, computed, input, model, signal } from '@angular/core';

import { duration, eventValue } from '../../core/format';
import { Profiles } from '../../core/models';
import { OCHRE } from '../../core/palette';

/** Geometry of the drawing (SVG user units). */
const TOP = 64;
const BOTTOM = 456;
const LEFT = 58;
const RIGHT = 138;
const PLOT_LEFT = 168;
const PLOT_RIGHT = 232;

@Component({
  selector: 'app-column-view',
  templateUrl: './column-view.html',
  styleUrl: './column-view.scss',
})
export class ColumnView implements OnDestroy {
  profiles = input.required<Profiles>();
  bedHeight = input.required<number>();
  color = input.required<string>();
  /** index into profiles.t, two-way bound so the chart can show the same moment */
  frame = model(0);

  readonly ochre = OCHRE;
  readonly geo = { TOP, BOTTOM, LEFT, RIGHT, PLOT_LEFT, PLOT_RIGHT };
  readonly duration = duration;

  playing = signal(false);
  private raf = 0;
  private last = 0;

  nFrames = computed(() => this.profiles().t.length);
  time = computed(() => this.profiles().t[this.safeFrame()] ?? 0);
  safeFrame = computed(() => Math.min(this.frame(), this.nFrames() - 1));

  slices = computed(() => {
    const p = this.profiles();
    const n = p.zeta.length;
    const h = (BOTTOM - TOP) / n;
    const q = p.q[this.safeFrame()];
    return p.zeta.map((_, i) => ({ y: TOP + i * h, h: h + 0.6, q: q[i] }));
  });

  gasLine = computed(() => this.polyline(this.profiles().c[this.safeFrame()]));
  solidLine = computed(() => this.polyline(this.profiles().q[this.safeFrame()]));

  outlet = computed(() => {
    const c = this.profiles().c[this.safeFrame()];
    return c[c.length - 1];
  });

  /** Position of the mass transfer zone = where the bed is half loaded. */
  front = computed(() => {
    const p = this.profiles();
    const q = p.q[this.safeFrame()];
    const i = q.findIndex(v => v < 0.5);
    if (i <= 0) return null;
    const zeta = p.zeta[i - 1] + (p.zeta[i] - p.zeta[i - 1]) * (q[i - 1] - 0.5) / (q[i - 1] - q[i]);
    return { y: TOP + zeta * (BOTTOM - TOP), depth: zeta * this.bedHeight() };
  });

  loadedShare = computed(() => {
    const q = this.profiles().q[this.safeFrame()];
    return q.reduce((a, b) => a + b, 0) / q.length;
  });

  ticks = computed(() => {
    const h = this.bedHeight();
    return [0, 0.25, 0.5, 0.75, 1].map(f => ({ y: TOP + f * (BOTTOM - TOP), label: `${(f * h).toFixed(1)} m` }));
  });

  toggle(): void {
    if (this.playing()) {
      this.stop();
      return;
    }
    if (this.safeFrame() >= this.nFrames() - 1) this.frame.set(0);
    this.playing.set(true);
    this.last = performance.now();
    this.raf = requestAnimationFrame(t => this.tick(t));
  }

  scrub(e: Event): void {
    this.stop();
    this.frame.set(eventValue(e));
  }

  private tick(now: number): void {
    if (now - this.last > 70) {
      this.last = now;
      const next = this.safeFrame() + 1;
      if (next >= this.nFrames()) {
        this.stop();
        return;
      }
      this.frame.set(next);
    }
    this.raf = requestAnimationFrame(t => this.tick(t));
  }

  private stop(): void {
    cancelAnimationFrame(this.raf);
    this.playing.set(false);
  }

  private polyline(values: number[]): string {
    const zeta = this.profiles().zeta;
    return values
      .map((v, i) => `${(PLOT_LEFT + v * (PLOT_RIGHT - PLOT_LEFT)).toFixed(1)},${(TOP + zeta[i] * (BOTTOM - TOP)).toFixed(1)}`)
      .join(' ');
  }

  ngOnDestroy(): void {
    this.stop();
  }
}
