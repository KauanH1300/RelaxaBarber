import { DIAS_SEMANA } from '../../services/horarios';
import type { DiaHorario } from '../../services/horarios';

export function SemanaExpediente({ dias, editavel, ocupado, alterar }: {
  dias: DiaHorario[]; editavel: boolean; ocupado: boolean; alterar: (dia: DiaHorario) => void;
}) {
  return <div className="expediente-semana">
    {dias.map((dia) => <fieldset key={dia.dia_semana} className="expediente-dia" disabled={!editavel || ocupado}>
      <legend>{DIAS_SEMANA[dia.dia_semana]}</legend>
      <label className="expediente-aberto"><input type="checkbox" checked={!dia.fechado}
        onChange={(e) => alterar({ ...dia, fechado: !e.target.checked, hora_inicio: '', hora_fim: '' })} />
        {dia.fechado ? 'Fechado' : 'Aberto'}</label>
      {dia.fechado ? <p className="expediente-fechado">Sem atendimento</p> : <div className="expediente-intervalo">
        <label>Abertura<input aria-label={`Abertura de ${DIAS_SEMANA[dia.dia_semana]}`} type="time" step="any" required
          value={dia.hora_inicio ?? ''} onChange={(e) => alterar({ ...dia, hora_inicio: e.target.value })} /></label>
        <span aria-hidden="true">—</span>
        <label>Fechamento<input aria-label={`Fechamento de ${DIAS_SEMANA[dia.dia_semana]}`} type="time" step="any" required
          value={dia.hora_fim ?? ''} onChange={(e) => alterar({ ...dia, hora_fim: e.target.value })} /></label>
      </div>}
    </fieldset>)}
  </div>;
}
