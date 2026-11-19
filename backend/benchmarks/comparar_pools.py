"""Mede pool frio, pool aquecido, lotes e serialização sem banco ou rede."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
import os
import pickle
from statistics import median
from time import perf_counter, process_time

from benchmarks.otimizacao_agenda import gerar_cenario, medir
from app.services.otimizacao_agenda import (avaliar_sequencial, avaliar_paralelo,
    avaliar_paralelo_lotes, ordenar_horarios, pontuar_lote)


def _registrar_processo(fila):
    fila.put(os.getpid())


def _cpu_lote(lote):
    inicio=process_time()
    resultado=pontuar_lote(lote)
    return resultado, process_time()-inicio


def criar_pool_aquecido(processos):
    contexto=get_context('spawn'); fila=contexto.Queue()
    inicio=perf_counter()
    pool=ProcessPoolExecutor(max_workers=processos,mp_context=contexto,
                             initializer=_registrar_processo,initargs=(fila,))
    try:
        tarefas=[pool.submit(os.getpid) for _ in range(processos)]
        pids={fila.get(timeout=30) for _ in range(processos)}
        assert len(pids)==processos
        for tarefa in tarefas: tarefa.result(timeout=30)
        return pool,fila,perf_counter()-inicio
    except BaseException:
        pool.shutdown(wait=True,cancel_futures=True); fila.close(); raise


def frio_lotes(candidatos,processos,tamanho):
    with ProcessPoolExecutor(max_workers=processos,mp_context=get_context('spawn')) as pool:
        return avaliar_paralelo_lotes(candidatos,processos,tamanho,pool)


def executar(repeticoes):
    disponiveis=os.cpu_count() or 1
    if hasattr(os,'sched_getaffinity'):
        disponiveis=min(disponiveis,len(os.sched_getaffinity(0)))
    print(f'cpus_disponiveis={disponiveis} repeticoes={repeticoes}',flush=True)
    for nome,dias,profissionais in (('pequeno',1,2),('medio',7,12),('grande',30,50)):
        candidatos=gerar_cenario(dias,profissionais)
        seq,base=medir(lambda:avaliar_sequencial(candidatos),repeticoes)
        ranking=ordenar_horarios(candidatos,base)
        serializar,blob=medir(lambda:pickle.dumps(candidatos,protocol=pickle.DEFAULT_PROTOCOL),repeticoes)
        desserializar,copia=medir(lambda:pickle.loads(blob),repeticoes)
        assert copia==candidatos
        print(f'cenario={nome} candidatos={len(candidatos)} seq_ms={seq*1000:.3f} '
              f'pickle_kib={len(blob)/1024:.1f} pickle_ms={serializar*1000:.3f} '
              f'unpickle_ms={desserializar*1000:.3f}',flush=True)
        for processos in (1,2,4):
            if processos>disponiveis:
                print(f'  p={processos} ignorado=cpus_insuficientes',flush=True); continue
            inicializacoes=[]
            for _ in range(repeticoes):
                pool,fila,tempo=criar_pool_aquecido(processos)
                inicializacoes.append(tempo);pool.shutdown(wait=True);fila.close();fila.join_thread()
            frio,resultado_frio=medir(lambda:avaliar_paralelo(candidatos,processos),repeticoes)
            frio256,resultado_frio256=medir(lambda:frio_lotes(candidatos,processos,256),repeticoes)
            pool,fila,_=criar_pool_aquecido(processos)
            try:
                aquecido,resultado=medir(lambda:avaliar_paralelo(candidatos,processos,pool),repeticoes)
                medidas={}
                for tamanho in (64,256,1024):
                    valor,novo=medir(lambda:avaliar_paralelo_lotes(candidatos,processos,tamanho,pool),repeticoes)
                    assert novo==base and ordenar_horarios(candidatos,novo)==ranking
                    medidas[tamanho]=valor
                blocos=[candidatos[i:i+256] for i in range(0,len(candidatos),256)]
                tempos_cpu=[]
                for _ in range(repeticoes):
                    cpu_resultados=list(pool.map(_cpu_lote,blocos,chunksize=1))
                    assert [x for bloco,_ in cpu_resultados for x in bloco]==base
                    tempos_cpu.append(sum(tempo for _,tempo in cpu_resultados))
                cpu=median(tempos_cpu)
            finally:
                pool.shutdown(wait=True);fila.close();fila.join_thread()
            assert resultado==resultado_frio==resultado_frio256==base
            print(f'  p={processos} startup_ms={median(inicializacoes)*1000:.3f} '
                  f'frio_atual_ms={frio*1000:.3f} aquecido_atual_ms={aquecido*1000:.3f} '
                  f'aquecido_64_ms={medidas[64]*1000:.3f} aquecido_256_ms={medidas[256]*1000:.3f} '
                  f'aquecido_1024_ms={medidas[1024]*1000:.3f} frio_256_ms={frio256*1000:.3f} '
                  f'cpu_lotes_ms={cpu*1000:.3f} speedup_aquecido256={seq/medidas[256]:.4f} '
                  f'eficiencia_aquecido256={seq/medidas[256]/processos:.4f} equivalente=True',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--repeticoes',type=int,default=5)
    args=parser.parse_args()
    if args.repeticoes<5: parser.error('Use pelo menos cinco repetições')
    executar(args.repeticoes)
