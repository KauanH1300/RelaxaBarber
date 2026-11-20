"""Fechamento e repasses: autorização no FastAPI, lançamentos imutáveis no banco."""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import text
from app.models import PerfilEnum
from app.services import filiais
from app.services.errors import SemPermissao, FilialObrigatoria, RecursoNaoEncontrado
from app.services.financeiro_errors import AcessoFinanceiroNegado, EntradaFinanceiraInvalida, EstadoFinanceiroIncompativel, ConflitoIdempotenciaFinanceira
from app.services.persistencia import transacao_escrita
from app.services.regras_financeiras import fingerprint
from app.services.repasses_calculo import EventoAcumulado, ParcelaCongelada, demonstrar, estados_atuais

ZERO = Decimal('0.00')


def contexto(db, usuario, filial_id, profissional_id, escrita=False):
    try:
        ator = filiais.usuario_atual(db, usuario, bloquear=escrita)
        if ator.perfil != PerfilEnum.ADMIN:
            raise SemPermissao('Sem permissão para repasses')
        filial = filiais.resolver_filial(db, ator, filial_id, bloquear=escrita)
        filiais.validar_profissional(db, profissional_id, filial.id)
        return ator, filial
    except (SemPermissao, FilialObrigatoria, RecursoNaoEncontrado):
        raise AcessoFinanceiroNegado('Sem acesso ao profissional ou filial') from None


def _travar(db, filial, profissional):
    # Serializa fechamentos, pagamentos e estornos do mesmo profissional.
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:contexto, 0))'),
               {'contexto': f'repasse:{filial}:{profissional}'})
    # Usa a mesma trava que protege alterações de comanda e eventos financeiros.
    return list(db.execute(text('''SELECT c.id FROM public.comandas c WHERE c.filial_id=:filial AND
        (EXISTS (SELECT 1 FROM public.comissoes_item i WHERE i.comanda_id=c.id AND i.profissional_id=:profissional)
         OR EXISTS (SELECT 1 FROM public.eventos_comissao e WHERE e.comanda_id=c.id AND e.profissional_id=:profissional))
        ORDER BY c.id FOR UPDATE OF c'''), {'filial':filial,'profissional':profissional}).scalars())


def _dados(db, filial, profissional, inicio, fim, bloqueadas=None):
    params={'filial':filial,'profissional':profissional,'bloqueadas':None if bloqueadas is None else [str(x) for x in bloqueadas]}
    linhas=db.execute(text('''SELECT e.item_id,e.id,e.profissional_id,e.filial_id,e.ordem,
        COALESCE(a.data, (c.data_abertura AT TIME ZONE 'America/Recife')::date) origem,e.gerada,e.liberada
        FROM public.eventos_comissao e JOIN public.comandas c ON c.id=e.comanda_id
        LEFT JOIN public.agendamentos a ON a.id=c.agendamento_id
        WHERE e.filial_id=:filial AND (CAST(:bloqueadas AS uuid[]) IS NULL OR c.id=ANY(CAST(:bloqueadas AS uuid[])))
        AND e.item_id IN (SELECT item_id FROM public.eventos_comissao WHERE filial_id=:filial AND profissional_id=:profissional)
        ORDER BY e.ordem'''),params).all()
    if any(r.origem is None for r in linhas): raise EstadoFinanceiroIncompativel('Comissão sem data de origem')
    estados=estados_atuais([EventoAcumulado(r.item_id,r.id,r.profissional_id,r.filial_id,r.ordem,r.origem,r.gerada,r.liberada) for r in linhas],profissional,filial)
    parcelas=db.execute(text('''SELECT p.id,p.item_id,p.valor,
        row_number() OVER (ORDER BY f.registrado_em,f.id,p.id) ordem,
        COALESCE((SELECT sum(a.valor) FROM public.alocacoes_repasse a WHERE a.parcela_id=p.id),0)-
        COALESCE((SELECT sum(ae.valor) FROM public.alocacoes_estorno_repasse ae WHERE ae.parcela_id=p.id),0) pago
        FROM public.parcelas_repasse p JOIN public.fechamentos_repasse f ON f.id=p.fechamento_id
        WHERE p.filial_id=:filial AND p.profissional_id=:profissional'''),params).all()
    try:
        calculo=demonstrar(estados,[ParcelaCongelada(p.id,p.item_id,p.ordem,p.valor,p.pago) for p in parcelas],inicio,fim)
    except ValueError:
        raise EstadoFinanceiroIncompativel('Histórico de comissão requer conciliação') from None
    return estados,calculo


def resumo_por_origem(db, filial_id, profissional_id, inicio, fim):
    _, resumo = _dados(db, filial_id, profissional_id, inicio, fim)
    return dict(gerada=resumo.gerada, liberada=resumo.liberada,
                elegivel=resumo.elegivel_periodo, paga=resumo.pago_liquido_periodo)


def consultar(db, usuario, filial_id, profissional_id, inicio, fim):
    _,filial=contexto(db,usuario,filial_id,profissional_id)
    if inicio>fim: raise EntradaFinanceiraInvalida('Período inválido')
    estados, resumo=_dados(db,filial.id,profissional_id,inicio,fim)
    itens={r.id:r for r in db.execute(text('SELECT id,descricao,tipo FROM public.itens_comanda WHERE id=ANY(CAST(:ids AS uuid[]))'),
        {'ids':[str(e.item_id) for e in estados]}).all()}
    fechamentos=db.execute(text('''SELECT id,inicio,fim,valor,registrado_por,registrado_em FROM public.fechamentos_repasse
        WHERE filial_id=:filial AND profissional_id=:profissional ORDER BY registrado_em DESC,id'''),{'filial':filial.id,'profissional':profissional_id}).mappings().all()
    pagamentos=db.execute(text('''SELECT p.id,p.fechamento_id,p.valor,p.metodo,p.data_pagamento,p.registrado_por,p.registrado_em,
        COALESCE((SELECT sum(e.valor) FROM public.estornos_repasse e WHERE e.pagamento_id=p.id),0) estornado
        FROM public.pagamentos_repasse p WHERE p.filial_id=:filial AND p.profissional_id=:profissional ORDER BY p.registrado_em DESC,p.id'''),{'filial':filial.id,'profissional':profissional_id}).mappings().all()
    vinculos=dict(db.execute(text('SELECT id,fechamento_id FROM public.parcelas_repasse WHERE filial_id=:filial AND profissional_id=:profissional'),{'filial':filial.id,'profissional':profissional_id}).all())
    estornos=db.execute(text('''SELECT e.id,e.pagamento_id,e.fechamento_id,e.valor,e.motivo,e.registrado_por,e.registrado_em
        FROM public.estornos_repasse e JOIN public.fechamentos_repasse f ON f.id=e.fechamento_id
        WHERE f.filial_id=:filial AND f.profissional_id=:profissional ORDER BY e.registrado_em DESC,e.id'''),{'filial':filial.id,'profissional':profissional_id}).mappings().all()
    return {'gerada':resumo.gerada,'liberada':resumo.liberada,'pendente':resumo.pendente_recebimento,
        'elegivel':resumo.elegivel_periodo,'deficit_pago':resumo.deficit_pago,'bloqueado':resumo.bloqueio_por_deficit,
        'itens':[{'item_id':e.item_id,'evento_id':e.evento_id,'origem':e.origem,'descricao':itens[e.item_id].descricao,'tipo':itens[e.item_id].tipo,'gerada':e.gerada,'liberada':e.liberada,'elegivel':resumo.credito_por_item.get(e.item_id,ZERO)} for e in estados if inicio<=e.origem<=fim],
        'parcelas':[{'id':p.parcela_id,'fechamento_id':vinculos[p.parcela_id],'congelado':p.congelado,'pago':p.pago_liquido,'disponivel':p.disponivel,'ajuste_negativo':p.ajuste_negativo} for p in resumo.parcelas],
        'fechamentos':[dict(f) for f in fechamentos],'pagamentos':[dict(p) for p in pagamentos],'estornos':[dict(e) for e in estornos]}


def _replay(db,tabela,where,params,esperado):
    linha=db.execute(text(f'SELECT id,fingerprint FROM public.{tabela} WHERE {where}'),params).first()
    if linha and linha.fingerprint != esperado: raise ConflitoIdempotenciaFinanceira('Chave já utilizada')
    return str(linha.id) if linha else None


def fechar(db,usuario,filial_id,profissional_id,inicio,fim,chave):
    if inicio>fim: raise EntradaFinanceiraInvalida('Período inválido')
    esperado=fingerprint('fechamento_repasse',filial=filial_id,profissional=profissional_id,inicio=inicio.isoformat(),fim=fim.isoformat())
    with transacao_escrita(db):
        ator,filial=contexto(db,usuario,filial_id,profissional_id,True)
        # A unicidade da chave é por filial, inclusive entre profissionais.
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:contexto, 0))'),
                   {'contexto': f'repasse-chave:{filial.id}:{chave}'})
        bloqueadas=_travar(db,filial.id,profissional_id)
        anterior=_replay(db,'fechamentos_repasse','filial_id=:filial AND chave=:chave',{'filial':filial.id,'chave':chave},esperado)
        if anterior: return {'id':anterior}
        estados,r=_dados(db,filial.id,profissional_id,inicio,fim,bloqueadas)
        if r.bloqueio_por_deficit or r.elegivel_periodo<=ZERO: raise EstadoFinanceiroIncompativel('Nenhum crédito disponível ou há débito pendente')
        ident=uuid4()
        db.execute(text('''INSERT INTO public.fechamentos_repasse(id,filial_id,profissional_id,inicio,fim,valor,registrado_por,chave,fingerprint)
            VALUES (:id,:filial,:profissional,:inicio,:fim,:valor,:ator,:chave,:fp)'''),dict(id=ident,filial=filial.id,profissional=profissional_id,inicio=inicio,fim=fim,valor=r.elegivel_periodo,ator=ator.id,chave=chave,fp=esperado))
        for e in estados:
            valor=r.credito_por_item.get(e.item_id,ZERO)
            if valor>ZERO:
                db.execute(text('''INSERT INTO public.parcelas_repasse(id,fechamento_id,filial_id,profissional_id,item_id,evento_id,origem,valor)
                    VALUES (:id,:fechamento,:filial,:profissional,:item,:evento,:origem,:valor)'''),dict(id=uuid4(),fechamento=ident,filial=filial.id,profissional=profissional_id,item=e.item_id,evento=e.evento_id,origem=e.origem,valor=valor))
        return {'id':str(ident)}


def _fechamento(db,ident,filial,profissional):
    f=db.execute(text('SELECT id,inicio,fim FROM public.fechamentos_repasse WHERE id=:id AND filial_id=:filial AND profissional_id=:profissional'),dict(id=ident,filial=filial,profissional=profissional)).first()
    if not f: raise AcessoFinanceiroNegado('Fechamento indisponível')
    return f


def pagar(db,usuario,filial_id,profissional_id,fechamento_id,valor,metodo,data_pagamento,chave):
    if not valor.is_finite() or valor<=ZERO or valor!=valor.quantize(Decimal('.01')) or metodo not in ('pix','dinheiro','transferencia') or data_pagamento.tzinfo is None or data_pagamento>datetime.now(timezone.utc):
        raise EntradaFinanceiraInvalida('Dados de repasse inválidos')
    esperado=fingerprint('pagamento_repasse',fechamento=fechamento_id,valor=valor,metodo=metodo,data=data_pagamento.isoformat())
    with transacao_escrita(db):
        ator,filial=contexto(db,usuario,filial_id,profissional_id,True);bloqueadas=_travar(db,filial.id,profissional_id)
        f=_fechamento(db,fechamento_id,filial.id,profissional_id)
        anterior=_replay(db,'pagamentos_repasse','fechamento_id=:id AND chave=:chave',{'id':f.id,'chave':chave},esperado)
        if anterior:return {'id':anterior}
        _,r=_dados(db,filial.id,profissional_id,f.inicio,f.fim,bloqueadas)
        ids=set(db.execute(text('SELECT id FROM public.parcelas_repasse WHERE fechamento_id=:id'),{'id':f.id}).scalars())
        saldos=[p for p in r.parcelas if p.parcela_id in ids and p.disponivel>ZERO]
        if r.bloqueio_por_deficit or valor>sum((p.disponivel for p in saldos),ZERO): raise EstadoFinanceiroIncompativel('Saldo insuficiente')
        ident=uuid4();db.execute(text('''INSERT INTO public.pagamentos_repasse(id,fechamento_id,filial_id,profissional_id,valor,metodo,data_pagamento,registrado_por,chave,fingerprint)
          VALUES (:id,:fechamento,:filial,:profissional,:valor,:metodo,:data,:ator,:chave,:fp)'''),dict(id=ident,fechamento=f.id,filial=filial.id,profissional=profissional_id,valor=valor,metodo=metodo,data=data_pagamento,ator=ator.id,chave=chave,fp=esperado))
        restante=valor
        for p in saldos:
            quantia=min(restante,p.disponivel)
            if quantia:db.execute(text('INSERT INTO public.alocacoes_repasse(pagamento_id,parcela_id,fechamento_id,valor) VALUES (:pagamento,:parcela,:fechamento,:valor)'),dict(pagamento=ident,parcela=p.parcela_id,fechamento=f.id,valor=quantia));restante-=quantia
            if restante==ZERO:break
        return {'id':str(ident)}


def estornar(db,usuario,filial_id,profissional_id,fechamento_id,pagamento_id,valor,motivo,chave):
    if not valor.is_finite() or valor<=ZERO or valor!=valor.quantize(Decimal('.01')) or not motivo.strip():raise EntradaFinanceiraInvalida('Dados de estorno inválidos')
    esperado=fingerprint('estorno_repasse',pagamento=pagamento_id,valor=valor,motivo=motivo.strip())
    with transacao_escrita(db):
        ator,filial=contexto(db,usuario,filial_id,profissional_id,True);_travar(db,filial.id,profissional_id)
        f=_fechamento(db,fechamento_id,filial.id,profissional_id)
        anterior=_replay(db,'estornos_repasse','fechamento_id=:id AND chave=:chave',{'id':f.id,'chave':chave},esperado)
        if anterior:return {'id':anterior}
        pagamento=db.execute(text('SELECT id,valor FROM public.pagamentos_repasse WHERE id=:id AND fechamento_id=:f'),{'id':pagamento_id,'f':f.id}).first()
        if not pagamento:raise AcessoFinanceiroNegado('Pagamento indisponível')
        linhas=db.execute(text('''SELECT a.parcela_id,a.valor-COALESCE((SELECT sum(e.valor) FROM public.alocacoes_estorno_repasse e
          WHERE e.pagamento_id=a.pagamento_id AND e.parcela_id=a.parcela_id),0) disponivel FROM public.alocacoes_repasse a
          WHERE a.pagamento_id=:id ORDER BY a.parcela_id'''),{'id':pagamento_id}).all()
        if valor>sum((r.disponivel for r in linhas),ZERO):raise EstadoFinanceiroIncompativel('Estorno excede pagamento')
        ident=uuid4();db.execute(text('''INSERT INTO public.estornos_repasse(id,pagamento_id,fechamento_id,valor,motivo,registrado_por,chave,fingerprint)
          VALUES (:id,:pagamento,:fechamento,:valor,:motivo,:ator,:chave,:fp)'''),dict(id=ident,pagamento=pagamento_id,fechamento=f.id,valor=valor,motivo=motivo.strip(),ator=ator.id,chave=chave,fp=esperado))
        restante=valor
        for linha in linhas:
            quantia=min(restante,linha.disponivel)
            if quantia:db.execute(text('INSERT INTO public.alocacoes_estorno_repasse(estorno_id,pagamento_id,parcela_id,valor) VALUES (:estorno,:pagamento,:parcela,:valor)'),dict(estorno=ident,pagamento=pagamento_id,parcela=linha.parcela_id,valor=quantia));restante-=quantia
            if restante==ZERO:break
        return {'id':str(ident)}
