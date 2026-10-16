import axios from 'axios';
import { invalidarSessao, obterToken } from './sessao';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  const token = obterToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (resposta) => resposta,
  (erro: unknown) => {
    if (axios.isAxiosError(erro)) {
      invalidarSessao(erro.response?.status, erro.config?.url, erro.config?.headers?.Authorization);
    }
    return Promise.reject(erro);
  },
);

export default api;