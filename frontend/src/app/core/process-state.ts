import { Injectable, signal } from '@angular/core';

/** What the feed line delivers, so the cycle page can start from it. */
export interface FeedHandOff {
  fluid: string;
  outlet_C: number;
  composition: Record<string, number>;
  reducer_barg: number;
  mass_flow: number;
}

@Injectable({ providedIn: 'root' })
export class ProcessState {
  readonly feed = signal<FeedHandOff | null>(null);
}
