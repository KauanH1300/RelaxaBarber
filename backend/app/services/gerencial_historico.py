"""Projeção paginada dos registros originais de auditoria."""
from sqlalchemy import text

from app.services.gerencial import limites

# Cada fonte aparece uma vez. Eventos derivados de comissão continuam no detalhe da comanda.
AUDITORIAS = {
    'recebimento': ('pagamentos_comanda', 'id', 'comanda_id', 'NULL'),
    'estorno': ('estornos_pagamento', 'id', 'comanda_id', 'motivo'),
    'fechamento': ('fechamentos_financeiros_comanda', 'comanda_id', 'comanda_id', 'motivo'),
    'habilitacao': ('controles_financeiros_comanda', 'comanda_id', 'comanda_id', 'motivo'),
    'beneficio': ('beneficios_comanda', 'id', 'comanda_id', 'motivo'),
    'inclusao_servico': ('inclusoes_servicos_comanda', 'id', 'comanda_id', 'NULL'),
    'alteracao_item': ('alteracoes_itens_comanda', 'id', 'comanda_id', 'motivo'),
    'cancelamento_comanda': ('cancelamentos_comanda', 'comanda_id', 'comanda_id', 'motivo'),
    'estoque': ('movimentos_estoque', 'id', 'produto_id', 'motivo'),
    'repasse_fechamento': ('fechamentos_repasse', 'id', 'profissional_id', 'NULL'),
    'repasse_pagamento': ('pagamentos_repasse', 'id', 'profissional_id', 'NULL'),
}

FONTES = {
    tipo: f"""SELECT '{tipo}' tipo, {id_} id, {referencia} referencia, registrado_em,
                     registrado_por autor, false autor_cliente, CAST({motivo} AS text) motivo
              FROM public.{tabela} WHERE filial_id=:filial AND registrado_em>=:desde AND registrado_em<:ate"""
    for tipo, (tabela, id_, referencia, motivo) in AUDITORIAS.items()
}
FONTES.update({
    'nao_comparecimento': """SELECT 'nao_comparecimento', id, id, falta_registrada_em,
           falta_registrada_por, false, falta_motivo FROM public.agendamentos
           WHERE filial_id=:filial AND falta_registrada_em>=:desde AND falta_registrada_em<:ate""",
    'repasse_estorno': """SELECT 'repasse_estorno', e.id, f.profissional_id, e.registrado_em,
           e.registrado_por, false, e.motivo FROM public.estornos_repasse e
           JOIN public.fechamentos_repasse f ON f.id=e.fechamento_id
           WHERE f.filial_id=:filial AND e.registrado_em>=:desde AND e.registrado_em<:ate""",
    'cancelamento_agendamento': """SELECT 'cancelamento_agendamento', id, id, cancelado_em,
           COALESCE(cancelado_por,cancelado_por_cliente), cancelado_por_cliente IS NOT NULL, motivo_cancelamento
           FROM public.agendamentos WHERE filial_id=:filial AND cancelado_em>=:desde AND cancelado_em<:ate""",
    'reagendamento': """SELECT 'reagendamento', r.id, r.agendamento_id, r.registrado_em,
           COALESCE(r.registrado_por,r.registrado_por_cliente), r.registrado_por_cliente IS NOT NULL, r.motivo
           FROM public.reagendamentos r JOIN public.agendamentos a ON a.id=r.agendamento_id
           WHERE a.filial_id=:filial AND r.registrado_em>=:desde AND r.registrado_em<:ate""",
})


def consultar(db, filial, inicio, fim, tipo, pagina, tamanho):
    desde, ate = limites(filial, inicio, fim)
    fontes = [FONTES[tipo]] if tipo else list(FONTES.values())
    uniao = ' UNION ALL '.join(fontes)
    parametros = dict(filial=filial.id, desde=desde, ate=ate, limite=tamanho, deslocamento=(pagina - 1) * tamanho)
    consulta = text(f"""
        WITH eventos(tipo,id,referencia,registrado_em,autor,autor_cliente,motivo) AS ({uniao}),
        pagina AS (
            SELECT * FROM eventos ORDER BY registrado_em DESC,tipo,id
            LIMIT :limite OFFSET :deslocamento
        )
        SELECT pagina.*, contagem.total FROM (SELECT count(*) total FROM eventos) contagem
        LEFT JOIN pagina ON true ORDER BY registrado_em DESC,tipo,id
    """)
    linhas = db.execute(consulta, parametros).mappings().all()
    return dict(total=linhas[0]['total'], pagina=pagina, tamanho=tamanho,
                itens=[{k: v for k, v in linha.items() if k != 'total'} for linha in linhas if linha['id']])

