"""Classificação pura de horários já considerados válidos pela agenda.

Não consulta banco, não verifica disponibilidade e não confirma reservas.
"""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context
import logging
import os
from threading import BoundedSemaphore


@dataclass(frozen=True)
class Candidato:
    profissional: str
    inicio: int
    duracao: int
    janela_inicio: int
    janela_fim: int


def pontuar(candidato: Candidato):
    """Prioriza menos sobras curtas, menos fragmentos e encaixe na borda.

    Desempates: horário crescente e identificador estável do profissional.
    """
    antes = candidato.inicio - candidato.janela_inicio
    depois = candidato.janela_fim - candidato.inicio - candidato.duracao
    if antes < 0 or depois < 0:
        raise ValueError('Candidato fora da janela')
    sobras = (antes, depois)
    return (sum(0 < x < 30 for x in sobras), sum(x > 0 for x in sobras),
            min(sobras), -max(sobras), candidato.inicio, candidato.profissional)


def candidatos_da_disponibilidade(profissional: str, horarios: list[str], duracao: int):
    """Converte sequências de inícios válidos em janelas discretizadas de 15 min."""
    minutos = sorted({int(h[:2]) * 60 + int(h[3:]) for h in horarios})
    resultado = []
    inicio = 0
    while inicio < len(minutos):
        fim = inicio + 1
        while fim < len(minutos) and minutos[fim] == minutos[fim - 1] + 15:
            fim += 1
        janela_inicio, janela_fim = minutos[inicio], minutos[fim - 1] + duracao
        resultado.extend(Candidato(profissional, m, duracao, janela_inicio, janela_fim)
                         for m in minutos[inicio:fim])
        inicio = fim
    return resultado


def avaliar_sequencial(candidatos):
    return list(map(pontuar, candidatos))


def pontuar_lote(candidatos):
    """Avalia um lote sem alterar a função de pontuação ou a ordem."""
    return [pontuar(candidato) for candidato in candidatos]


def avaliar_paralelo_lotes(candidatos, processos, tamanho_lote, executor):
    if processos < 1 or tamanho_lote < 1:
        raise ValueError('Processos e tamanho do lote devem ser positivos')
    lotes = (candidatos[i:i + tamanho_lote] for i in range(0, len(candidatos), tamanho_lote))
    return [pontuacao for lote in executor.map(pontuar_lote, lotes, chunksize=1) for pontuacao in lote]


def avaliar_paralelo(candidatos, processos, executor=None):
    if not candidatos:
        return []
    tamanho = max(1, len(candidatos) // (processos * 4))
    if executor is not None:
        return list(executor.map(pontuar, candidatos, chunksize=tamanho))
    with ProcessPoolExecutor(max_workers=processos, mp_context=get_context('spawn')) as pool:
        return list(pool.map(pontuar, candidatos, chunksize=tamanho))


def ordenar_horarios(candidatos, pontuacoes):
    """Retorna cada horário uma vez, usando a melhor pontuação entre profissionais."""
    if len(candidatos) != len(pontuacoes):
        raise ValueError('Quantidade de pontuações incompatível')
    melhores = {}
    for candidato, pontuacao in zip(candidatos, pontuacoes):
        if candidato.inicio not in melhores or pontuacao < melhores[candidato.inicio]:
            melhores[candidato.inicio] = pontuacao
    return [f'{minuto // 60:02d}:{minuto % 60:02d}'
            for minuto in sorted(melhores, key=melhores.get)]


# Configuração exclusivamente no servidor; uma requisição nunca fornece processos.
_paralelo_em_uso = BoundedSemaphore(1)
MAX_PROCESSOS = min(4, os.cpu_count() or 1)
MIN_CANDIDATOS_PARALELO = 48


def recomendar(candidatos):
    estrategia = os.getenv('AGENDAMENTO_OTIMIZACAO_ESTRATEGIA', 'sequencial').strip().lower()
    if estrategia not in ('sequencial', 'paralelo'):
        logging.getLogger(__name__).warning('Estratégia de otimização inválida; usando execução sequencial')
        estrategia = 'sequencial'
    if (estrategia == 'paralelo' and len(candidatos) >= MIN_CANDIDATOS_PARALELO
            and MAX_PROCESSOS > 1 and _paralelo_em_uso.acquire(blocking=False)):
        try:
            try:
                pontuacoes = avaliar_paralelo(candidatos, MAX_PROCESSOS)
            except Exception:
                logging.getLogger(__name__).warning('Otimização paralela indisponível; usando execução sequencial')
                pontuacoes = avaliar_sequencial(candidatos)
        finally:
            _paralelo_em_uso.release()
    else:
        pontuacoes = avaliar_sequencial(candidatos)
    return ordenar_horarios(candidatos, pontuacoes)
