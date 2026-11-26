import axios from 'axios';
import type { InternalAxiosRequestConfig } from 'axios';
import { contextoAtual, contextoValido, recursoPorFilial, EVENTO_ACESSO_FILIAIS } from './filialAtiva';
import type { MarcaContexto } from './filialAtiva';
type ConfigFilial = InternalAxiosRequestConfig & { marcaFilial?: MarcaContexto; geracaoSessao?: string | null };
import { invalidarSessao, obterToken } from './sessao';
import { EVENTO_ESTOQUE_ATUALIZADO, podeAlterarEstoque } from './eventosEstoque';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''),
  timeout: 15000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(async (config) => {
  (config as ConfigFilial).geracaoSessao = obterToken();
  if (config.url !== '/auth/csrf' && !['get', 'head', 'options'].includes(config.method ?? 'get')) {
    const { data } = await api.post<{ csrf: string }>('/auth/csrf');
    if ((config as ConfigFilial).geracaoSessao !== obterToken()) throw new axios.CanceledError('A sessão mudou.');
    config.headers['X-Equipe-CSRF'] = data.csrf;
  }
  const token = obterToken();

  if (recursoPorFilial(config.url)) {
    const marca = contextoAtual();
    if (marca.token && (!marca.filialId || marca.token !== token)) throw new axios.CanceledError('Selecione uma filial autorizada');
    if (marca.filialId && marca.token === token) {
      if (config.params?.filial_id && config.params.filial_id !== marca.filialId) throw new axios.CanceledError('Contexto da operação alterado');
      (config as ConfigFilial).marcaFilial = marca;
      config.params = { ...config.params, filial_id: marca.filialId };
      if (config.method === 'post' && /^\/(agendamentos(?:\/(?:encaixes|bloqueios))?|clientes)$/.test(config.url ?? '')) {
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
    if (marca && podeAlterarEstoque(resposta.config.url, resposta.config.method)) {
      window.dispatchEvent(new Event(EVENTO_ESTOQUE_ATUALIZADO));
    }
    return resposta;
  },
  (erro: unknown) => {
    if (axios.isAxiosError(erro)) {
      const marca = (erro.config as ConfigFilial | undefined)?.marcaFilial;
      if (marca && (!contextoValido(marca) || obterToken() !== marca.token)) return Promise.reject(new axios.CanceledError('Resposta de outra filial descartada'));
      if (erro.response?.status === 403 && marca) window.dispatchEvent(new Event(EVENTO_ACESSO_FILIAIS));
      invalidarSessao(erro.response?.status, erro.config?.url, (erro.config as ConfigFilial | undefined)?.geracaoSessao);
    }
    return Promise.reject(erro);
  },
);

export default api;
