# Otimização de encaixes e comparação de execução

O mecanismo de disponibilidade continua sendo a fonte dos candidatos: ele verifica
filial, jornada, pausas, reservas existentes e duração dos serviços. A confirmação
continua revalidando o horário. A API mantém `horarios` em ordem cronológica e
acrescenta até três `recomendados`, sempre contidos na lista original.

Para cada profissional, sequências de inícios válidos com passo de 15 minutos
definem janelas discretizadas. A pontuação prefere, nesta ordem: menos sobras
menores que 30 minutos, menos fragmentos, menor sobra de borda e maior outra
sobra. Empates usam início e identificador do profissional. Para um mesmo horário,
é usada a melhor pontuação entre os profissionais disponíveis. As janelas são uma
aproximação baseada na grade de horários válidos, não uma medição exata de cada
minuto livre. A recomendação não reserva horários nem garante disponibilidade futura.

O padrão é `AGENDAMENTO_OTIMIZACAO_ESTRATEGIA=sequencial`. O valor `paralelo` é
opcional e configurado somente no servidor. Ele usa `ProcessPoolExecutor`, no
máximo quatro processos, uma execução paralela simultânea por processo do servidor
e somente a partir de 48 candidatos. Outras requisições usam a mesma pontuação
sequencial; se o pool falhar, ocorre fallback sequencial. Em uma implantação com
vários processos do servidor, cada processo tem seu próprio limite. O limiar é
uma proteção operacional, não uma previsão de ganho: nos testes abaixo, o modo
paralelo não compensou. O cliente não controla a estratégia nem o número de processos.

## Reprodução

A professora autorizou o uso do modo paralelo para comparação experimental e
demonstração no RNF01. Os benchmarks sustentam a escolha do modo sequencial
como padrão de operação. O RNF02 é demonstrado pelos tempos, speedup e
eficiência registrados abaixo.

Com as dependências do backend instaladas, na pasta `backend`:

```sh
PYTHONPATH=. python benchmarks/otimizacao_agenda.py --repeticoes 5
```

No PowerShell, defina `$env:PYTHONPATH='.'` antes do comando Python. O benchmark
não acessa banco nem rede. Ele usa uma semente fixa, expedientes de dez horas,
intervalo de almoço e reservas de 30, 45 ou 60 minutos. Os cenários agregam dias
e profissionais para avaliar lotes de pontuação; o maior é um experimento em lote,
não uma estimativa da quantidade de candidatos de uma única requisição.

Cada número é a mediana de cinco repetições com `perf_counter`. `nucleo_ms` mede
o envio e a pontuação com pool já aquecido; `total_ms` também inclui criar e
encerrar o pool. A diferença entre as medianas é uma estimativa do custo do ciclo
de vida do pool, não uma medição independente. `speedup_total` é sequencial
dividido pelo total paralelo; eficiência é speedup dividido pelo número de
processos. A ordenação é verificada quanto à equivalência fora dos tempos. O
tempo total de uma requisição HTTP, consultas ao banco e validação de agenda não
foi medido por este benchmark e não deve ser inferido desses valores.

## Resultado observado

Execução local em contêiner Linux x86_64, Python 3.12.16, quatro CPUs lógicas,
cinco repetições. Os valores variam com a máquina e a carga concorrente.

| Cenário | Candidatos | Sequencial (ms) | Processos | Núcleo aquecido (ms) | Total paralelo (ms) | Speedup total | Eficiência | Equivalente |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Pequeno | 24 | 0,076 | 1 | 3,233 | 626,469 | 0,0001 | 0,0001 | Sim |
| Pequeno | 24 | 0,076 | 2 | 5,204 | 451,360 | 0,0002 | 0,0001 | Sim |
| Pequeno | 24 | 0,076 | 4 | 13,138 | 809,601 | 0,0001 | 0,0000 | Sim |
| Médio | 1.390 | 2,309 | 1 | 7,693 | 268,617 | 0,0086 | 0,0086 | Sim |
| Médio | 1.390 | 2,309 | 2 | 8,722 | 380,895 | 0,0061 | 0,0030 | Sim |
| Médio | 1.390 | 2,309 | 4 | 32,234 | 672,303 | 0,0034 | 0,0009 | Sim |
| Grande | 24.248 | 51,689 | 1 | 140,119 | 464,106 | 0,1114 | 0,1114 | Sim |
| Grande | 24.248 | 51,689 | 2 | 109,960 | 419,163 | 0,1233 | 0,0617 | Sim |
| Grande | 24.248 | 51,689 | 4 | 101,817 | 880,276 | 0,0587 | 0,0147 | Sim |

Neste ambiente, serialização e criação dos processos custaram mais do que a
pontuação sequencial em todos os cenários. O modo sequencial permanece padrão;
não há evidência destes resultados para afirmar ganho em produção.

## Investigação de pool reutilizado e lotes

Execute, nas mesmas condições e com pelo menos cinco repetições:

```sh
PYTHONPATH=. python benchmarks/comparar_pools.py --repeticoes 5
```

O programa usa os mesmos candidatos, `pontuar` e desempates da aplicação e
verifica igualdade das pontuações e do ranking. Compara o pool criado por
avaliação, o pool com todos os trabalhadores iniciados previamente e lotes
explícitos de 64, 256 e 1.024 candidatos. No pool aquecido, o tempo ainda inclui
distribuição, serialização, IPC e coleta dos resultados. O tempo frio inclui a
criação e o encerramento do pool. A inicialização é medida separadamente, com
todos os processos confirmando que iniciaram; ela não é necessariamente igual à
diferença entre as medianas fria e aquecida, pois o pool frio pode criar processos
de forma preguiçosa. Os valores incluem o ciclo de vida do pool, mas não HTTP ou
acesso ao banco.

Para investigar custo de dados, são medidas separadamente a serialização e a
desserialização com `pickle` da lista completa; os tamanhos e tempos são uma
referência, não o volume exato transferido pelo executor, que envia lotes
separados. `CPU lote` é a mediana da soma do `process_time` gasto pelos processos
na função de pontuação para lotes de 256. É tempo de CPU agregado, não tempo de
espera da requisição; IPC e serialização ficam fora dessa medição.

Resultados observados em contêiner Linux x86_64, Python 3.12.16, quatro CPUs
lógicas disponíveis, Intel Core i3-1005G1, sem limite de quota de CPU informado
pelo cgroup; cinco repetições por medição. Medições anteriores e novas ocorreram
em momentos diferentes e podem variar com a carga da máquina.

| Cenário | Candidatos | Sequencial novo (ms) | Pickle / leitura (ms) | Tamanho serializado |
|---|---:|---:|---:|---:|
| Pequeno | 24 | 0,083 | 0,061 / 0,046 | 0,9 KiB |
| Médio | 1.390 | 2,266 | 1,696 / 1,462 | 49,1 KiB |
| Grande | 24.248 | 47,895 | 62,130 / 59,636 | 859,7 KiB |

| Cenário | Processos | Frio anterior (ms) | Frio novo (ms) | Iniciar todos (ms) | Aquecido anterior (ms) | Aquecido novo (ms) | Lote 256 aquecido (ms) | Lote 256 frio (ms) | CPU lote (ms) | Speedup / eficiência aquecido 256 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Pequeno | 1 | 626,469 | 268,988 | 303,319 | 3,233 | 1,588 | 0,562 | 318,442 | 0,039 | 0,1484 / 0,1484 |
| Pequeno | 2 | 451,360 | 318,902 | 319,651 | 5,204 | 3,246 | 0,662 | 324,459 | 0,044 | 0,1260 / 0,0630 |
| Pequeno | 4 | 809,601 | 637,146 | 475,518 | 13,138 | 8,857 | 0,944 | 280,829 | 0,049 | 0,0884 / 0,0221 |
| Médio | 1 | 268,617 | 430,033 | 250,199 | 7,693 | 13,179 | 12,693 | 272,372 | 5,261 | 0,1785 / 0,1785 |
| Médio | 2 | 380,895 | 360,653 | 290,972 | 8,722 | 7,673 | 6,988 | 322,526 | 4,511 | 0,3242 / 0,1621 |
| Médio | 4 | 672,303 | 519,820 | 617,949 | 32,234 | 13,314 | 6,213 | 625,495 | 3,825 | 0,3647 / 0,0912 |
| Grande | 1 | 464,106 | 503,579 | 285,214 | 140,119 | 164,124 | 135,667 | 394,612 | 80,339 | 0,3530 / 0,3530 |
| Grande | 2 | 419,163 | 409,245 | 334,031 | 109,960 | 98,275 | 139,963 | 476,565 | 112,141 | 0,3422 / 0,1711 |
| Grande | 4 | 880,276 | 1.344,257 | 508,486 | 101,817 | 154,790 | 144,426 | 920,064 | 108,372 | 0,3316 / 0,0829 |

Os lotes de 64 e 1.024 também são impressos pelo script. No cenário médio com
dois processos, por exemplo, os resultados aquecidos foram 13,650 ms e 6,313 ms;
com quatro processos e cenário grande, foram 329,819 ms e 155,006 ms. Todos os
resultados foram equivalentes. Lotes ajudaram em alguns casos, mas não em todos;
serializar o cenário grande por si só já custou mais que a mediana sequencial.

Um pool persistente pode ser implementado por processo de servidor, criado após
o início de cada worker Uvicorn e encerrado no ciclo de vida da aplicação, com
limites de concorrência e recuperação de falha. Não foi habilitado na aplicação:
além dessas obrigações operacionais, os resultados aquecidos continuaram atrás
do sequencial. O experimento usa `spawn`, disponível em Windows e Linux, mas esta
medição e os testes foram executados somente em Linux; não se afirma validação
de ciclo de vida com FastAPI/Uvicorn no Windows. A execução sequencial continua
recomendada e o fallback existente foi preservado.
