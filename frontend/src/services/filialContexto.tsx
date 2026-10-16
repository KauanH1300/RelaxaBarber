import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import api from './api';
import { obterToken } from './sessao';
import { mensagemErro } from './erros';
import { EVENTO_ACESSO_FILIAIS, filialRestauravel, lerPreferencia, salvarPreferencia, mudarContexto } from './filialAtiva';
import type { Filial } from './filialAtiva';
import { Contexto } from './filialEstado';

export function FilialProvider({ usuarioId, token, children }: { usuarioId: string; token: string; children: ReactNode }) {
  const [filiais, setFiliais] = useState<Filial[]>([]);
  const [filialId, setFilialId] = useState<string | null>(null);
  const [versao, setVersao] = useState(0);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState('');
  const selecionada = useRef<string | null>(null);
  const sequencia = useRef(0);
  const escolher = useCallback((id: string | null) => {
    selecionada.current = id;
    setFilialId(id);
    salvarPreferencia(usuarioId, id);
    setVersao(mudarContexto(token, id).versao);
  }, [usuarioId, token]);

  useEffect(() => {
    let ativo = true;
    mudarContexto(token, null);
    async function atualizar(invalidar = false) {
      const tentativa = ++sequencia.current;
      if (invalidar) {
        setFiliais([]);
        selecionada.current = null;
        setFilialId(null);
        setVersao(mudarContexto(token, null).versao);
        setCarregando(true);
      }
      try {
        const { data } = await api.get<Filial[]>('/filiais');
        if (!ativo || tentativa !== sequencia.current || obterToken() !== token) return;
        const id = filialRestauravel(data, selecionada.current ?? lerPreferencia(usuarioId));
        setFiliais(data);
        if (id !== selecionada.current || invalidar) escolher(id);
        else if (!id) salvarPreferencia(usuarioId, null);
        setErro('');
      } catch (falha) {
        if (!ativo || tentativa !== sequencia.current || obterToken() !== token) return;
        setErro(mensagemErro(falha, 'Não foi possível validar as filiais'));
      } finally {
        if (ativo && tentativa === sequencia.current) setCarregando(false);
      }
    }
    const revalidar = () => { void atualizar(true); };
    const foco = () => { void atualizar(); };
    const timer = window.setInterval(foco, 30000);
    window.addEventListener(EVENTO_ACESSO_FILIAIS, revalidar);
    window.addEventListener('focus', foco);
    void atualizar();
    return () => {
      ativo = false;
      window.clearInterval(timer);
      window.removeEventListener(EVENTO_ACESSO_FILIAIS, revalidar);
      window.removeEventListener('focus', foco);
      mudarContexto(null, null);
    };
  }, [token, usuarioId, escolher]);

  function selecionar(id: string) {
    if (id === selecionada.current || !filiais.some((f) => f.id === id)) return;
    ++sequencia.current; // Não deixa uma revalidação antiga desfazer a escolha.
    escolher(id);
    setCarregando(false);
  }
  function recarregar() { window.dispatchEvent(new Event(EVENTO_ACESSO_FILIAIS)); }
  return <Contexto.Provider value={{ filiais, filialId, versao, carregando, erro, selecionar, recarregar }}>{children}</Contexto.Provider>;
}
