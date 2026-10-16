import axios from 'axios';
import type { InternalAxiosRequestConfig } from 'axios';
import { contextoAtual, contextoValido, recursoPorFilial, EVENTO_ACESSO_FILIAIS } from './filialAtiva';
import type { MarcaContexto } from './filialAtiva';
type ConfigFilial = InternalAxiosRequestConfig & { marcaFilial?: MarcaContexto };
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
  if (recursoPorFilial(config.url)) {
    const marca = contextoAtual();
    if (marca.token && (!marca.filialId || marca.token !== token)) throw new axios.CanceledError('Selecione uma filial autorizada');
    if (marca.filialId && marca.token === token) {
      if (config.params?.filial_id && config.params.filial_id !== marca.filialId) throw new axios.CanceledError('Contexto da operação alterado');
      (config as ConfigFilial).marcaFilial = marca;
      config.params = { ...config.params, filial_id: marca.filialId };
      if (config.method === 'post' && /^\/(agendamentos|clientes)$/.test(config.url ?? '')) {
        if (config.data?.filial_id && config.data.filial_id !== marca.filialId) throw new axios.CanceledError('Contexto do formulário alterado');
        config.data = { ...config.data, filial_id: marca.filialId };
      }
    }
  }
  return config;
});

api.interceptors.response.use(
  (resposta) => {
    const marca = (resposta.config as ConfigFilial).marcaFilial;
    if (marca && (!contextoValido(marca) || obterToken() !== marca.token)) throw new axios.CanceledError('Resposta de outra filial descartada');
    return resposta;
  },
  (erro: unknown) => {
    if (axios.isAxiosError(erro)) {
      const marca = (erro.config as ConfigFilial | undefined)?.marcaFilial;
      if (marca && (!contextoValido(marca) || obterToken() !== marca.token)) return Promise.reject(new axios.CanceledError('Resposta de outra filial descartada'));
      if (erro.response?.status === 403 && marca) window.dispatchEvent(new Event(EVENTO_ACESSO_FILIAIS));
      invalidarSessao(erro.response?.status, erro.config?.url, erro.config?.headers?.Authorization);
    }
    return Promise.reject(erro);
  },
);

export default api;