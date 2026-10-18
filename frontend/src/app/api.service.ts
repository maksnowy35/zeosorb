import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { BreakthroughRequest, BreakthroughResponse, Materials, MatrixResponse } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = '/api';

  materials(): Observable<Materials> {
    return this.http.get<Materials>(`${this.base}/materials`);
  }

  breakthrough(req: BreakthroughRequest): Observable<BreakthroughResponse> {
    return this.http.post<BreakthroughResponse>(`${this.base}/breakthrough`, req);
  }

  matrix(req: Omit<BreakthroughRequest, 'refrigerant' | 'zeolite'>): Observable<MatrixResponse> {
    const params = new HttpParams({ fromObject: { ...req } });
    return this.http.get<MatrixResponse>(`${this.base}/matrix`, { params });
  }
}
