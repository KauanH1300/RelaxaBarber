import axios from 'axios';
import { useEffect, useRef, useState } from 'react';
import { useFilial } from '../../services/filialEstado';
import { useUsuario } from '../../services/usuario';
import { DIAS_SEMANA, chaveRascunho, consultarHorarios, diasDaResposta, erroHorarios, lerRascunho, podeEditarHorarios, salvarHorarios, serializarHorarios } from '../../services/horarios';
import type { DiaHorario, SemanaHorario } from '../../services/horarios';
import { SemanaExpediente } from './SemanaExpediente';
import './horarios.css';

export function HorariosFilial() {
  const { filialId, filiais } = useFilial();
  const usuario = useUsuario();
  // O Layout remonta o Outlet quando muda a filial ou a sessão.
  return filialId ? <EditorHorarios key={`${usuario.id}:${filialId}`} filialId={filialId} nome={filiais.find((f) => f.id === filialId)?.nome ?? 'Filial'} /> : null;
}

function EditorHorarios({ filialId, nome }: { filialId: string; nome: string }) {
  const usuario = useUsuario();
  const [semana, setSemana] = useState<SemanaHorario | null>(null);
  const [dias, setDias] = useState<DiaHorario[]>([]);
  const [pendente, setPendente] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [conferindo, setConferindo] = useState(false);
  const [erro, setErro] = useState('');
  const [sucesso, setSucesso] = useState('');
  const [aviso, setAviso] = useState('');
  const [negado, setNegado] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  const montado = useRef(false);
  const enviando = useRef(false);
  const chave = chaveRascunho(usuario.id, filialId);
  const editavel = podeEditarHorarios(usuario) && !negado;

  useEffect(() => {
    montado.current = true;
    const controller = new AbortController();
    consultarHorarios(filialId, controller.signal).then((data) => {
      if (controller.signal.aborted) return;
      setSemana(data); setDias(diasDaResposta(data)); setErro(''); setCarregando(false); setNegado(false);
      if (podeEditarHorarios(usuario)) {
        try {
          const rascunho = lerRascunho(sessionStorage.getItem(chave));
          if (rascunho) { setDias(rascunho); setPendente(true); setAviso('Rascunho recuperado neste navegador. Compare com a semana salva antes de salvar.'); }
        } catch { setAviso('O navegador não permite guardar rascunhos. Salve antes de sair.'); }
      }
    }).catch((falha: unknown) => {
      if (!controller.signal.aborted && !axios.isCancel(falha)) { setErro(erroHorarios(falha)); setCarregando(false); }
    });
    return () => { montado.current = false; controller.abort(); };
  }, [filialId, chave, tentativa, usuario]);

  useEffect(() => {
    if (!pendente && !salvando) return;
    const sair = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const navegar = (event: MouseEvent) => {
      if (!(event.target instanceof Element) || !event.target.closest('a[href], button[title="Sair"]')) return;
      if (!window.confirm(salvando ? 'O salvamento está em andamento. Sair mesmo assim?' : 'Há alterações não salvas. Sair desta tela?')) {
        event.preventDefault(); event.stopPropagation();
      }
    };
    const trocar = (event: Event) => {
      if (!(event.target instanceof Element) || !event.target.matches('select[aria-label="Filial ativa"]')) return;
      if (!window.confirm('Há alterações não salvas. Trocar de filial?')) {
        event.stopPropagation(); (event.target as HTMLSelectElement).value = filialId;
      }
    };
    window.addEventListener('beforeunload', sair);
    document.addEventListener('click', navegar, true);
    document.addEventListener('change', trocar, true);
    return () => { window.removeEventListener('beforeunload', sair); document.removeEventListener('click', navegar, true); document.removeEventListener('change', trocar, true); };
  }, [pendente, salvando, filialId]);

  function alterar(dia: DiaHorario) {
    if (!editavel || salvando) return;
    const novos = dias.map((d) => d.dia_semana === dia.dia_semana ? dia : d);
    setDias(novos); setPendente(true); setSucesso(''); setErro('');
    try { sessionStorage.setItem(chave, JSON.stringify(novos)); }
    catch { setAviso('Não foi possível guardar o rascunho. Salve antes de sair.'); }
  }
  function descartar() {
    if (!semana || salvando || (pendente && !window.confirm('Descartar as alterações e mostrar a última semana carregada?'))) return;
    setDias(diasDaResposta(semana)); setPendente(false); setErro(''); setSucesso(''); setAviso('');
    try { sessionStorage.removeItem(chave); } catch { /* Armazenamento opcional. */ }
  }
  async function conferirSemana() {
    if (enviando.current || conferindo) return;
    setConferindo(true);
    try {
      const data = await consultarHorarios(filialId);
      if (!montado.current) return;
      setSemana(data);
      setAviso('Semana salva consultada. Confira os dados abaixo; seu rascunho foi preservado.');
    } catch (falha) {
      if (montado.current && !axios.isCancel(falha)) setErro(erroHorarios(falha));
    } finally { if (montado.current) setConferindo(false); }
  }
  async function salvar(event: React.FormEvent) {
    event.preventDefault();
    if (!editavel || !pendente || enviando.current || conferindo || !semana) return;
    try { serializarHorarios(dias); } catch (falha) { setErro((falha as Error).message); return; }
    enviando.current = true; setSalvando(true); setErro(''); setSucesso('');
    try {
      const data = await salvarHorarios(filialId, dias, usuario);
      if (!montado.current) return;
      setSemana(data); setDias(diasDaResposta(data)); setPendente(false); setAviso(''); setSucesso('Expediente salvo com sucesso.');
      try { sessionStorage.removeItem(chave); } catch { /* Armazenamento opcional. */ }
    } catch (falha) {
      if (montado.current && !axios.isCancel(falha)) {
        setErro(erroHorarios(falha, true));
        if (axios.isAxiosError(falha) && falha.response?.status === 403) setNegado(true);
      }
    } finally { enviando.current = false; if (montado.current) setSalvando(false); }
  }
  return <section className="expediente" aria-labelledby="expediente-titulo" aria-busy={carregando || salvando}>
    <header><p className="expediente-eyebrow">Gestão da unidade</p><h1 id="expediente-titulo">Horários de funcionamento</h1><p>{nome} · Semana de segunda a domingo</p></header>
    {carregando && <p role="status">Carregando expediente...</p>}
    {erro && <p className="expediente-erro" role="alert">{erro}</p>}
    {sucesso && <p className="expediente-sucesso" role="status">{sucesso}</p>}
    {aviso && <p className="expediente-aviso" role="status">{aviso}</p>}
    {!carregando && !semana && <button type="button" onClick={() => { setCarregando(true); setTentativa((n) => n + 1); }}>Tentar novamente</button>}
    {semana && <>
      <div className="expediente-resumo"><strong>{semana.configurado ? 'Semana configurada' : 'Semana não configurada'}</strong>
        <p>{semana.configurado ? 'A agenda considera o expediente salvo para esta filial.' : 'Esta filial ainda segue o comportamento anterior, sem restrição por expediente. Nada muda até salvar os sete dias.'}</p>
        <p>Horários locais da filial. Abertura e fechamento devem ocorrer no mesmo dia.</p>
      </div>
      {!editavel && <p>Somente administradores podem editar e salvar o expediente.{negado ? ' Sua permissão foi recusada pelo servidor.' : ''}</p>}
      {!editavel && !semana.configurado ? <ol className="expediente-nao-configurada">{dias.map((d) => <li key={d.dia_semana}>{DIAS_SEMANA[d.dia_semana]} — Não configurado</li>)}</ol> : <form onSubmit={(event) => { void salvar(event); }}>
        <SemanaExpediente dias={dias} editavel={editavel} ocupado={salvando} alterar={alterar} />
        <footer className="expediente-acoes"><p role="status">{salvando ? 'Salvando expediente...' : pendente ? 'Alterações não salvas' : 'Nenhuma alteração pendente'}</p>
          {pendente && <button type="button" disabled={salvando} onClick={descartar}>Descartar alterações</button>}
          {editavel && <button className="expediente-salvar" type="submit" disabled={!pendente || salvando || conferindo}>{salvando ? 'Salvando...' : 'Salvar expediente'}</button>}
        </footer>
      </form>}
      {editavel && <details className="expediente-comparacao"><summary>Conferir semana salva</summary>
        <p>Última consulta ao servidor; os campos de edição e o rascunho permanecem separados.</p>
        <button type="button" disabled={salvando || conferindo} onClick={() => { void conferirSemana(); }}>{conferindo ? 'Consultando...' : 'Consultar semana no servidor'}</button>
        {semana.configurado ? <ul>{[...semana.dias].sort((a, b) => a.dia_semana - b.dia_semana).map((d) => <li key={d.dia_semana}>{DIAS_SEMANA[d.dia_semana]}: {d.fechado ? 'Fechado' : `${d.hora_inicio} — ${d.hora_fim}`}</li>)}</ul> : <p>Nenhum expediente configurado no servidor.</p>}
      </details>}
      {editavel && <p className="expediente-nota">Se a nova semana conflitar com reservas existentes, o salvamento será recusado. Seus ajustes permanecerão na tela.</p>}
    </>}
  </section>;
}
