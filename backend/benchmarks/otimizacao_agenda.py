"""Benchmark reproduzível; nenhum banco, rede ou dado real é utilizado."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from random import Random
from statistics import median
from time import perf_counter

from app.services.otimizacao_agenda import (candidatos_da_disponibilidade,
    avaliar_sequencial, avaliar_paralelo, ordenar_horarios)


def gerar_cenario(dias, profissionais, seed=69):
    random=Random(seed); candidatos=[]
    for dia in range(dias):
        for profissional in range(profissionais):
            # Expediente 08:00–18:00, pausa 12:00–13:00 e reservas plausíveis
            # de 30/45/60 min, alinhadas à grade atual de 15 min.
            reservas=[(720,780)]
            for _ in range(6):
                inicio=random.randrange(32,69)*15
                duracao=random.choice((30,45,60))
                if inicio+duracao<=1080 and not any(inicio<b and inicio+duracao>a for a,b in reservas):
                    reservas.append((inicio,inicio+duracao))
            duracao=random.choice((30,45,60))
            opcoes=[f'{m//60:02d}:{m%60:02d}' for m in range(480,1080-duracao+1,15)
                    if not any(m<b and m+duracao>a for a,b in reservas)]
            candidatos.extend(candidatos_da_disponibilidade(f'{dia:03d}-{profissional:03d}',opcoes,duracao))
    return candidatos


def medir(funcao,repeticoes):
    tempos=[]; ultimo=None
    for _ in range(repeticoes):
        inicio=perf_counter(); ultimo=funcao(); tempos.append(perf_counter()-inicio)
    return median(tempos),ultimo


def executar(repeticoes):
    for nome,dias,profissionais in (('pequeno',1,2),('medio',7,12),('grande',30,50)):
        candidatos=gerar_cenario(dias,profissionais)
        seq,base=medir(lambda:avaliar_sequencial(candidatos),repeticoes)
        ranking=ordenar_horarios(candidatos,base)
        print(f'{nome}: dias={dias} profissionais={profissionais} candidatos={len(candidatos)} sequencial_ms={seq*1000:.3f}',flush=True)
        for processos in (1,2,4):
            with ProcessPoolExecutor(max_workers=processos,mp_context=get_context('spawn')) as pool:
                # A primeira execução aquece os processos e fica fora da mediana do núcleo.
                assert avaliar_paralelo(candidatos,processos,pool)==base
                aquecido,resultado=medir(lambda:avaliar_paralelo(candidatos,processos,pool),repeticoes)
            total,frio=medir(lambda:avaliar_paralelo(candidatos,processos),repeticoes)
            equivalente=(resultado==base and frio==base and ordenar_horarios(candidatos,resultado)==ranking)
            speedup=seq/total if total else 0
            print(f'  processos={processos} nucleo_ms={aquecido*1000:.3f} total_ms={total*1000:.3f} '
                  f'overhead_ms={(total-aquecido)*1000:.3f} speedup_total={speedup:.4f} '
                  f'eficiencia={speedup/processos:.4f} equivalente={equivalente}',flush=True)
            assert equivalente


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repeticoes',type=int,default=5)
    args=parser.parse_args()
    if args.repeticoes<3: parser.error('Use pelo menos 3 repetições')
    executar(args.repeticoes)
