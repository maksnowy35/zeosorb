import { Component, computed, input, output } from '@angular/core';

import { CycleStepResult } from '../../core/process-models';
import { MODE_COLORS, MODE_TEXT } from '../../core/palette';

export const MODE_LABEL: Record<string, string> = {
  fill: 'fill', adsorb: 'adsorb', blowdown: 'blow-down', evacuate: 'vacuum', purge: 'purge', idle: 'idle',
};

const LEFT = 52;
const RIGHT = 8;
const W = 1000;
const ROW = 34;
const TOP = 26;

@Component({
  selector: 'app-cycle-timeline',
  template: `
    <svg [attr.viewBox]="'0 0 ' + width + ' ' + height" role="img" [attr.aria-label]="aria()">
      @for (b of beds; track b; let r = $index) {
        <text [attr.x]="LEFT - 10" [attr.y]="TOP + r * (ROW + 8) + ROW / 2 + 5" class="bed" text-anchor="end">Bed {{ b }}</text>
      }
      @for (blk of blocks(); track blk.key) {
        <g class="block" [class.selected]="blk.index === selected()" (click)="pick.emit(blk.index)"
           (keydown.enter)="pick.emit(blk.index)" tabindex="0" role="button"
           [attr.aria-label]="'Step ' + blk.index + ', bed ' + blk.bed + ': ' + blk.mode">
          <rect [attr.x]="blk.x + 1" [attr.y]="blk.y" [attr.width]="blk.w - 2" [attr.height]="ROW" rx="3"
                [attr.fill]="blk.fill" />
          @if (blk.w > 46) {
            <text [attr.x]="blk.x + blk.w / 2" [attr.y]="blk.y + ROW / 2 + 5" text-anchor="middle" class="mode"
                  [attr.fill]="blk.ink">{{ blk.label }}</text>
          }
        </g>
      }
      @for (s of heads(); track s.index) {
        <text [attr.x]="s.x" y="16" text-anchor="middle" class="num" [class.on]="s.index === selected()">{{ s.index }}</text>
        @if (s.mark) {
          <g [attr.transform]="'translate(' + s.markX + ',' + s.markY + ')'">
            @if (s.mark === 'reached') {
              <path d="M-5 4 L0 -5 L5 4 Z" class="reached" />
            } @else {
              <circle r="4.5" class="missed" />
            }
          </g>
        }
      }
      <line [attr.x1]="LEFT" [attr.x2]="width - RIGHT" [attr.y1]="height - 18" [attr.y2]="height - 18" class="axis" />
      @for (t of ticks(); track t.x) {
        <line [attr.x1]="t.x" [attr.x2]="t.x" [attr.y1]="height - 18" [attr.y2]="height - 14" class="axis" />
        <text [attr.x]="t.x" [attr.y]="height - 2" text-anchor="middle" class="tick">{{ t.label }}</text>
      }
    </svg>
  `,
  styles: `
    :host { display: block; overflow-x: auto; }
    svg { width: 100%; min-width: 720px; height: auto; display: block; font-family: var(--font); }
    .bed { font-size: 13px; font-weight: 600; fill: var(--ink); }
    .mode { font-size: 12px; pointer-events: none; }
    .num { font-size: 12px; fill: var(--steel); font-variant-numeric: tabular-nums; }
    .num.on { fill: var(--ink); font-weight: 700; }
    .block { cursor: pointer; outline: none; }
    .block rect { stroke: transparent; stroke-width: 2; }
    .block:hover rect, .block:focus-visible rect { stroke: var(--steel); }
    .block.selected rect { stroke: var(--ink); }
    .reached { fill: var(--ink); }
    .missed { fill: var(--paper); stroke: var(--signal); stroke-width: 1.8; }
    .axis { stroke: var(--steel); stroke-width: 1; }
    .tick { font-size: 11px; fill: var(--steel); }
  `,
})
export class CycleTimeline {
  steps = input.required<CycleStepResult[]>();
  selected = input<number | null>(null);
  pick = output<number>();

  readonly beds = ['A', 'B'] as const;
  readonly LEFT = LEFT;
  readonly RIGHT = RIGHT;
  readonly ROW = ROW;
  readonly TOP = TOP;
  readonly width = W;
  readonly height = TOP + 2 * (ROW + 8) + 22;

  private total = computed(() => {
    const s = this.steps();
    const last = s[s.length - 1];
    return last ? last.t_start + last.duration : 1;
  });

  private x(t: number): number {
    return LEFT + (t / this.total()) * (W - LEFT - RIGHT);
  }

  blocks = computed(() => {
    const out = [];
    for (const s of this.steps()) {
      for (const [r, b] of (['A', 'B'] as const).entries()) {
        const mode = s.beds[b].mode;
        const x = this.x(s.t_start);
        out.push({
          key: `${s.index}-${b}`, index: s.index, bed: b, mode,
          x, w: Math.max(this.x(s.t_start + s.duration) - x, 1.5), y: TOP + r * (ROW + 8),
          fill: MODE_COLORS[mode], ink: MODE_TEXT[mode], label: MODE_LABEL[mode],
        });
      }
    }
    return out;
  });

  heads = computed(() => this.steps().map(s => {
    const x0 = this.x(s.t_start), x1 = this.x(s.t_start + s.duration);
    let mark: 'reached' | 'missed' | null = null;
    let markX = 0, markY = 0;
    if (s.control_bed && s.setpoint_barg !== null) {
      const row = s.control_bed === 'A' ? 0 : 1;
      mark = s.t_reach !== null || s.ended_by === 'setpoint' ? 'reached' : 'missed';
      const t = s.t_reach ?? s.duration;
      markX = Math.min(Math.max(this.x(s.t_start + t), x0 + 6), x1 - 6);
      markY = TOP + row * (ROW + 8) + ROW + 1;
    }
    return { index: s.index, x: (x0 + x1) / 2, mark, markX, markY };
  }));

  ticks = computed(() => {
    const total = this.total() / 3600;
    const step = total > 6 ? 1 : total > 2 ? 0.5 : 0.25;
    const out = [];
    for (let t = 0; t <= total + 1e-9; t += step) out.push({ x: this.x(t * 3600), label: `${t} h` });
    return out;
  });

  aria = computed(() => `Cycle timeline of ${this.steps().length} steps over ${(this.total() / 3600).toFixed(1)} h for beds A and B`);
}
