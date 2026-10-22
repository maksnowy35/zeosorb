import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, shareReplay } from 'rxjs';

import {
  BedParams, BreakthroughRequest, BreakthroughResponse, Materials, MatrixResponse,
  SeparationRequest, SeparationResponse, SweepRequest, SweepResponse,
} from './models';
import { CycleRequest, CycleResponse, FeedRequest, FeedResponse, ProcessDefaults } from './process-models';

@Injectable({ providedIn: 'root' })
export class Api {
  private http = inject(HttpClient);
  private base = '/api/v1';

  /** Material data never changes while the app is open - fetch once. */
  readonly materials$: Observable<Materials> = this.http
    .get<Materials>(`${this.base}/materials`)
    .pipe(shareReplay(1));

  breakthrough(req: BreakthroughRequest): Observable<BreakthroughResponse> {
    return this.http.post<BreakthroughResponse>(`${this.base}/breakthrough`, req);
  }

  matrix(params: BedParams): Observable<MatrixResponse> {
    const query: Record<string, string | number> = {};
    for (const [k, v] of Object.entries(params)) {
      if (v !== null && v !== undefined) query[k] = v;
    }
    return this.http.get<MatrixResponse>(`${this.base}/matrix`, { params: new HttpParams({ fromObject: query }) });
  }

  separation(req: SeparationRequest): Observable<SeparationResponse> {
    return this.http.post<SeparationResponse>(`${this.base}/separation`, req);
  }

  sweep(req: SweepRequest): Observable<SweepResponse> {
    return this.http.post<SweepResponse>(`${this.base}/sweep`, req);
  }

  readonly processDefaults$: Observable<ProcessDefaults> = this.http
    .get<ProcessDefaults>(`${this.base}/process/defaults`)
    .pipe(shareReplay(1));

  feed(req: FeedRequest): Observable<FeedResponse> {
    return this.http.post<FeedResponse>(`${this.base}/feed`, req);
  }

  feedSolve(req: FeedRequest & { segment: number; lo?: number; hi?: number }): Observable<FeedResponse> {
    return this.http.post<FeedResponse>(`${this.base}/feed/solve`, req);
  }

  cycle(req: CycleRequest): Observable<CycleResponse> {
    return this.http.post<CycleResponse>(`${this.base}/cycle`, req);
  }
}
