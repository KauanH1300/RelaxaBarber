import pytest
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from app.services import otimizacao_agenda as ot


def amostra():
    return (ot.candidatos_da_disponibilidade('prof-b', ['09:00','09:15','09:30','11:00','11:15'], 30)
            + ot.candidatos_da_disponibilidade('prof-a', ['09:00','09:15','10:00','10:15'], 30))


def test_janelas_nao_atravessam_lacunas_e_priorizam_bordas():
    candidatos=ot.candidatos_da_disponibilidade('p',['09:30','09:00','09:15','11:00'],30)
    assert [(c.janela_inicio,c.janela_fim) for c in candidatos]==[(540,600),(540,600),(540,600),(660,690)]
    resultado=ot.ordenar_horarios(candidatos,ot.avaliar_sequencial(candidatos))
    assert resultado[0]=='11:00' and set(resultado)=={'09:00','09:15','09:30','11:00'}


@pytest.mark.parametrize('processos',[1,2,4])
def test_estrategias_equivalentes_e_deterministicas(processos):
    candidatos=amostra()
    sequencial=ot.avaliar_sequencial(candidatos)
    paralelo=ot.avaliar_paralelo(candidatos,processos)
    assert sequencial==paralelo
    assert ot.ordenar_horarios(candidatos,sequencial)==ot.ordenar_horarios(candidatos,paralelo)
    assert ot.ordenar_horarios(candidatos,sequencial)==ot.ordenar_horarios(list(reversed(candidatos)),list(reversed(sequencial)))


def test_fallback_nao_remove_opcoes(monkeypatch):
    candidatos=amostra()*10
    monkeypatch.setenv('AGENDAMENTO_OTIMIZACAO_ESTRATEGIA','paralelo')
    monkeypatch.setattr(ot,'MAX_PROCESSOS',2)
    def falhar(*args,**kwargs): raise OSError('indisponível')
    monkeypatch.setattr(ot,'avaliar_paralelo',falhar)
    assert ot.recomendar(candidatos)==ot.ordenar_horarios(candidatos,ot.avaliar_sequencial(candidatos))


def test_vazio_limites_e_entrada_invalida():
    assert ot.recomendar([])==[] and ot.avaliar_paralelo([],2)==[]
    with pytest.raises(ValueError): ot.pontuar(ot.Candidato('p',500,30,510,600))
    with pytest.raises(ValueError): ot.ordenar_horarios(amostra(),[])
    with pytest.raises(ValueError): ot.avaliar_paralelo_lotes([],0,1,None)
    with pytest.raises(ValueError): ot.avaliar_paralelo_lotes([],1,0,None)


@pytest.mark.parametrize('tamanho',[1,3,64])
def test_lotes_reutilizados_preservam_ordem_e_pontuacao(tamanho):
    candidatos=amostra()*5
    with ProcessPoolExecutor(max_workers=2,mp_context=get_context('spawn')) as pool:
        esperado=ot.avaliar_sequencial(candidatos)
        for _ in range(2):
            resultado=ot.avaliar_paralelo_lotes(candidatos,2,tamanho,pool)
            assert resultado==esperado
            assert ot.ordenar_horarios(candidatos,resultado)==ot.ordenar_horarios(candidatos,esperado)
        assert ot.avaliar_paralelo_lotes([],2,tamanho,pool)==[]
