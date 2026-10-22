import { Component, computed, input } from '@angular/core';

import { FeedRequest, FeedResponse, SegmentIn } from '../../core/process-models';
import { tempColor } from '../../core/palette';

interface PipeDraw {
  x: number;
  w: number;
  y: number;
  h: number;
  seg: SegmentIn;
  stops: { offset: number; color: string }[];
  twoPhase: { x0: number; x1: number } | null;
  jacketColor: string | null;
  title: string;
  heating: string;
  duty: string;
  gradientId: string;
}

const X0 = 262;
const X1 = 820;
const MID = 128;

@Component({
  selector: 'app-line-schematic',
  templateUrl: './line-schematic.html',
  styleUrl: './line-schematic.scss',
})
export class LineSchematic {
  request = input.required<FeedRequest>();
  result = input.required<FeedResponse>();

  readonly mid = MID;

  ambient = computed(() => this.request().tank.T_amb_C);

  tank = computed(() => {
    const r = this.result();
    const req = this.request();
    const lf = Math.min(Math.max(r.tank.liquid_fraction[0] ?? 0.5, 0.02), 0.98);
    const top = 78, bottom = 178;
    const level = bottom - lf * (bottom - top);
    return {
      level,
      liquid: tempColor(r.tank.T_C[0], this.ambient()),
      vapour: tempColor(r.tank.T_C[0], this.ambient()),
      label: `${req.tank.volume_L.toFixed(0)} L, ${req.tank.fill_kg.toFixed(0)} kg`,
      state: `${r.tank.T_C[0].toFixed(0)} °C, ${r.reducer.p_in_bar.toFixed(1)} bar`,
      liquidOut: req.tank.withdrawal === 'liquid',
    };
  });

  pipes = computed<PipeDraw[]>(() => {
    const req = this.request();
    const res = this.result();
    const total = req.segments.reduce((a, s) => a + s.L_m, 0);
    const minW = 110;
    const avail = X1 - X0 - minW * req.segments.length;
    let x = X0;
    return req.segments.map((seg, i) => {
      const w = minW + avail * (seg.L_m / total);
      const h = Math.min(Math.max(seg.D_mm * 0.38, 7), 46);
      const sum = res.segments[i];
      const idx = res.line.z
        .map((z, k) => ({ z, k }))
        .filter(p => p.z >= sum.z_start - 1e-9 && p.z <= sum.z_end + 1e-9);
      const stops = idx.map(p => ({
        offset: (p.z - sum.z_start) / (sum.z_end - sum.z_start),
        color: tempColor(res.line.T_C[p.k], this.ambient()),
      }));
      const tp = idx.filter(p => res.line.x[p.k] !== null);
      const twoPhase = tp.length
        ? {
            x0: x + w * (tp[0].z - sum.z_start) / (sum.z_end - sum.z_start),
            x1: x + w * (tp[tp.length - 1].z - sum.z_start) / (sum.z_end - sum.z_start),
          }
        : null;
      const hd = seg.heating;
      const heating =
        hd.kind === 'medium' ? `jacket ${hd.T_medium_C.toFixed(0)} °C`
          : hd.kind === 'trace' ? `trace ${hd.q_trace_W_m.toFixed(0)} W/m`
            : hd.kind === 'insulated' ? `insulated ${hd.insulation_mm.toFixed(0)} mm`
              : 'bare pipe';
      const d: PipeDraw = {
        x, w, y: MID - h / 2, h, seg, stops, twoPhase,
        jacketColor: hd.kind === 'medium' ? tempColor(hd.T_medium_C, this.ambient()) : null,
        title: `${seg.name}: ${seg.D_mm.toFixed(0)} mm × ${seg.L_m.toFixed(1)} m`,
        heating,
        duty: `${sum.duty_W >= 0 ? '+' : '−'}${Math.abs(sum.duty_W) >= 1000 ? (Math.abs(sum.duty_W) / 1000).toFixed(2) + ' kW' : Math.abs(sum.duty_W).toFixed(0) + ' W'}`,
        gradientId: `seg-grad-${i}`,
      };
      x += w;
      return d;
    });
  });

  joints = computed(() => {
    const res = this.result();
    const pipes = this.pipes();
    return pipes.slice(0, -1).map((p, i) => ({ x: p.x + p.w, T: res.segments[i].T_out_C }));
  });

  inletT = computed(() => this.result().reducer.T_out_C);
  outlet = computed(() => this.result().outlet);
  outletColor = computed(() => tempColor(this.result().outlet.T_C, this.ambient()));
  pipeEnd = computed(() => {
    const p = this.pipes();
    const last = p[p.length - 1];
    return last ? last.x + last.w : X1;
  });

  ariaLabel = computed(() => {
    const r = this.result();
    return `Feed line: ${r.fluid} leaves the tank at ${r.reducer.T_in_C.toFixed(0)} °C, ` +
      `${r.reducer.T_out_C.toFixed(0)} °C after the reducer, ${r.outlet.T_C.toFixed(0)} °C at the adsorber.`;
  });
}
