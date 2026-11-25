# RNF03 — Validação local do tempo de resposta

**Resultado — CONCLUÍDO no cenário local avaliado.** As 240 requisições
ficaram abaixo do limite de 2 segundos, sem erros. O maior tempo HTTP foi
490,494 ms (490,5 ms arredondados), na criação de agendamento pelo portal.
A revisão avaliada da `develop` foi `03215f987a228e374986fd09b6e7775ab3072101`, com o PR #94.

## Resultados

Tempos em milissegundos. O p95 usa o método de posto mais próximo, com o
posto arredondado para cima. A coluna de aceite usa o máximo HTTP observado.

| Fluxo | Amostras | HTTP mediana | HTTP p95 | HTTP máximo | Backend mediana | Backend p95 | Backend máximo | Erros | Até 2 s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Disponibilidade por barbeiro | 30 | 22,043 | 169,994 | 184,420 | 20,526 | 162,497 | 179,890 | 0 | Sim |
| Sugestões na agenda interna | 30 | 29,948 | 137,951 | 141,305 | 28,642 | 132,416 | 136,698 | 0 | Sim |
| Disponibilidade no portal | 30 | 44,018 | 94,725 | 142,886 | 40,834 | 89,851 | 128,207 | 0 | Sim |
| Criação de agendamento interno | 30 | 67,598 | 247,609 | 264,979 | 66,172 | 246,466 | 262,398 | 0 | Sim |
| Criação de agendamento no portal | 30 | 127,732 | 294,755 | 490,494 | 124,327 | 290,568 | 484,933 | 0 | Sim |
| Início de atendimento agendado | 30 | 38,876 | 139,144 | 191,975 | 37,233 | 133,768 | 177,391 | 0 | Sim |
| Registro de atendimento imediato | 30 | 63,485 | 154,830 | 172,472 | 61,843 | 153,214 | 170,427 | 0 | Sim |
| Conclusão com baixa de insumo | 30 | 50,463 | 150,780 | 257,317 | 48,419 | 140,320 | 255,298 | 0 | Sim |

## Metodologia e limites

- O ensaio reutilizou as fixtures de integração do projeto, com dados fictícios, FastAPI servido por Uvicorn e PostgreSQL descartável em Docker. As requisições passaram pelas rotas HTTP e pelas regras reais da aplicação.
- Agenda interna e portal rodaram em duas sessões concorrentes. O atendimento imediato foi medido separadamente, com horário controlado para evitar sobreposição entre amostras. A conclusão incluiu baixa de insumo.
- A inicialização do ambiente e as cinco execuções de aquecimento por fluxo ficaram fora das amostras. A medição usou um relógio monotônico de alta resolução, sem latência artificial.
- O tempo HTTP vai do envio da requisição até a leitura do corpo completo em loopback. O tempo de backend vai da entrada na aplicação até o início da resposta, incluindo o acesso ao banco.
- A latência no ambiente publicado e o tempo percebido no navegador, do clique até a atualização da interface, ainda não foram medidos. O aceite vale para a carga e o ambiente locais descritos acima.
