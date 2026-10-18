import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { BreakthroughRequest, BreakthroughResponse, Materials } from './models';

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
}
