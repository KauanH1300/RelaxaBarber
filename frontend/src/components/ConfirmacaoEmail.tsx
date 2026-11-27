import { useEffect, useRef, useState } from 'react';
import { confirmarEmail, enviarConfirmacaoEmail } from '../services/auth';
import { mensagemErro } from '../services/erros';
import type { UsuarioLogado } from '../services/usuario';

export function ConfirmacaoEmail({ usuario, concluir, fechar, sair, saindo, erroSaida }: {
  usuario: UsuarioLogado;
  concluir: (usuario: UsuarioLogado) => void;
  fechar?: () => void;
  sair: () => void;
  saindo: boolean;
  erroSaida: string;
}) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const [pedido, setPedido] = useState('');
  const [codigo, setCodigo] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState('');
  const [reenvio, setReenvio] = useState(0);
  const [expira, setExpira] = useState(0);
  const [agora, setAgora] = useState(Date.now);
  const restantes = Math.max(0, Math.ceil((reenvio - agora) / 1000));
  const expirado = Boolean(pedido) && agora >= expira;

  useEffect(() => {
    const modal = dialogo.current;
    modal?.showModal();
    return () => modal?.close();
  }, []);
  useEffect(() => {
    const timer = window.setInterval(() => setAgora(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  async function enviar() {
    setOcupado(true);
    setErro('');
    try {
      const resposta = await enviarConfirmacaoEmail();
      const instante = Date.now();
      setAgora(instante);
      setReenvio(instante + resposta.reenvio_segundos * 1000);
      setExpira(instante + resposta.validade_segundos * 1000);
      setPedido(resposta.solicitacao_id);
      setCodigo('');
    } catch (falha) {
      setErro(mensagemErro(falha, 'Não foi possível enviar o código.'));
    } finally {
      setOcupado(false);
    }
  }

  async function confirmar() {
    setOcupado(true);
    setErro('');
    try {
      concluir(await confirmarEmail(pedido, codigo));
    } catch (falha) {
      setErro(mensagemErro(falha, 'Não foi possível confirmar o e-mail.'));
    } finally {
      setOcupado(false);
    }
  }

  return <dialog ref={dialogo} aria-labelledby="confirmacao-email-titulo"
    className="m-auto w-[min(28rem,calc(100%_-_2rem))] rounded-xl bg-surface-container p-6 text-on-surface backdrop:bg-black/70"
    onCancel={evento => { evento.preventDefault(); if (!ocupado) fechar?.(); }}>
    <h2 id="confirmacao-email-titulo" className="text-lg font-bold">Confirme seu e-mail</h2>
    <p className="my-3 break-words">Endereço cadastrado <strong>{usuario.email}</strong></p>
    {(erro || erroSaida) && <p role="alert" className="my-2 text-error">{erro || erroSaida}</p>}
    {pedido && <form className="my-3 space-y-2" onSubmit={evento => { evento.preventDefault(); void confirmar(); }}>
      <p role="status">{expirado ? 'O código expirou. Solicite um novo.' : 'Código enviado. Confira também o spam. O código vale por 10 minutos.'}</p>
      <label className="block">Código de seis dígitos
        <input value={codigo} onChange={evento => setCodigo(evento.target.value.replace(/\D/g, ''))}
          className="mt-1 block w-full rounded border border-outline p-2"
          inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required />
      </label>
      <button className="rounded bg-primary-container px-3 py-2 text-on-primary-container"
        disabled={ocupado || expirado || codigo.length !== 6}>Confirmar e-mail</button>
    </form>}
    <div className="mt-4 flex flex-wrap gap-3">
      <button type="button" className="underline" disabled={ocupado || restantes > 0} onClick={enviar}>
        {ocupado ? 'Aguarde…' : restantes ? `Reenviar em ${restantes}s` : pedido ? 'Reenviar código' : 'Solicitar código'}
      </button>
      {fechar ? <button type="button" disabled={ocupado} onClick={fechar}>Confirmar mais tarde</button>
        : <button type="button" disabled={ocupado || saindo} onClick={sair}>{saindo ? 'Encerrando…' : 'Encerrar sessão'}</button>}
    </div>
  </dialog>;
}
