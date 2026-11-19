import { lazy } from 'react';

export const Gerencial = lazy(() => import('./Gerencial').then(modulo => ({ default: modulo.Gerencial })));
