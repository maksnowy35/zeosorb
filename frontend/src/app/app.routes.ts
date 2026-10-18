import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    title: 'ZeoSorb · Simulator',
    loadComponent: () => import('./pages/simulator/simulator').then(m => m.Simulator),
  },
  {
    path: 'compare',
    title: 'ZeoSorb · Compare beds',
    loadComponent: () => import('./pages/compare/compare').then(m => m.Compare),
  },
  {
    path: 'separation',
    title: 'ZeoSorb · Separation',
    loadComponent: () => import('./pages/separation/separation').then(m => m.Separation),
  },
  {
    path: 'model',
    title: 'ZeoSorb · Model and sources',
    loadComponent: () => import('./pages/model/model').then(m => m.ModelPage),
  },
  { path: '**', redirectTo: '' },
];
