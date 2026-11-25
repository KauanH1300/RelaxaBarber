# RNF07 — Roteiro de usabilidade em QA

**Status — NÃO VERIFICADO.** Este documento é um plano de teste. O objetivo é
observar se o proprietário e a equipe conseguem aprender a usar a interface
em tarefas rotineiras, com atenção a pessoas com baixa familiaridade digital.
O critério de referência está na [definição do RNF07](requisitos.md#23-usabilidade).

## Preparação

- Use exclusivamente um ambiente de QA com dados fictícios e anote a revisão,
  a filial e o dispositivo usados. Prepare contas ativas com os perfis ADMIN,
  RECEPCAO e BARBEIRO comum. Abra a tela inicial da área interna com a conta e
  a filial corretas antes de começar o cronômetro.
- Prepare um serviço ativo, cliente fictício existente, profissional vinculado
  com jornada e um horário livre, produto ativo com saldo e mínimo conhecidos,
  relatório com dados fictícios para um período conhecido e reservas nos
  estados indicados abaixo. Use dados exclusivos por sessão ou reponha o
  cenário em QA entre sessões. Confira os resultados esperados antes do teste.
- Convide pelo menos duas pessoas representativas de cada perfil, com pelo
  menos uma de baixa familiaridade digital em cada grupo. Prefira participantes
  sem treinamento prévio no RelaxaBarber. Registre experiência prévia e
  familiaridade por autodeclaração. Use identificadores de sessão e guarde as
  fichas preenchidas fora do repositório.

## Sessão de 15 a 20 minutos

Reserve 2 a 3 minutos para explicar a sessão, até 12 minutos para as três
tarefas do perfil e 2 a 5 minutos para conversar sobre dificuldades. Informe
que a interface está sendo avaliada. Leia um enunciado de cada vez e entregue
somente os dados fictícios necessários. A coluna de verificação é para o
moderador.

| Perfil e tarefa | Enunciado para o participante | Verificação em QA |
|---|---|---|
| ADMIN 1 | Descubra o faturamento da unidade no período informado. | Selecionou o período correto no Gerencial e informou o valor esperado. |
| ADMIN 2 | Altere o estoque mínimo do produto informado para a quantidade solicitada. | Salvou o mínimo correto no produto indicado e verificou a confirmação. |
| ADMIN 3 | Reserve o intervalo indicado para que o profissional fique indisponível para novos agendamentos. | Criou o bloqueio na data, no intervalo e no profissional indicados e reconheceu a confirmação. |
| RECEPCAO 1 | Cadastre a pessoa fictícia informada usando os dados entregues. | Criou uma única ficha com nome e telefone. O e-mail pode ficar em branco. |
| RECEPCAO 2 | Marque o serviço para o cliente fictício existente, com o profissional, dia e horário informados. | Criou uma única reserva com os dados pedidos e reconheceu a confirmação. |
| RECEPCAO 3 | Registre que o cliente fictício de uma reserva já existente chegou. | A reserva correta passou de pendente para aguardando. |
| BARBEIRO 1 | Consulte seus atendimentos no dia informado e diga o horário e o serviço do cliente indicado. | Localizou a reserva na própria agenda e informou horário e serviço corretos. |
| BARBEIRO 2 | Inicie seu atendimento do cliente fictício indicado, que já chegou. | A própria reserva em espera passou para em atendimento. |
| BARBEIRO 3 | Conclua o atendimento do outro cliente indicado, que já está em atendimento. | A própria reserva indicada passou para concluído e a interface confirmou a ação. |

Use reservas distintas para as tarefas de consulta, início e conclusão quando
houver dependência de estado. Ao encerrar, pergunte qual etapa foi mais difícil
e o que a pessoa esperava encontrar naquela tela.

## Registro e aceite

- Cronometre da entrega do enunciado até a confirmação do resultado ou até
  **4 minutos**. Registre **concluiu sem ajuda**, **concluiu com ajuda** ou
  **não concluiu**. Repetir o enunciado literalmente não conta como ajuda.
  Uma dica sobre onde clicar ou como agir conta como ajuda e deve ser registrada.
- Registre ações incorretas relevantes, como selecionar a pessoa, data ou
  produto errado, ou enviar repetidamente por não entender a confirmação.
  Considere crítico confirmar uma gravação incorreta, duplicar um registro ou
  alterar uma reserva de outra pessoa. Registre os erros mesmo quando corrigidos
  durante a tarefa. Indisponibilidade de QA invalida a tentativa. Documente
  a ocorrência e refaça com um cenário fictício equivalente.
- **Aprovação proposta.** Execute as três tarefas com todos os participantes
  previstos. Em cada perfil, pelo menos 80% das tentativas válidas devem ser
  concluídas sem ajuda, no tempo limite e sem erro crítico. Cada tarefa deve
  ter pelo menos uma conclusão sem ajuda no seu perfil. Um erro crítico em
  qualquer sessão impede o aceite. Mantenha o RNF07 como NÃO VERIFICADO enquanto
  faltar evidência dos três perfis.

**Ficha por participante** — ID ______ · Perfil ______ · Revisão de QA ______
· Filial fictícia ______ · Dispositivo ______ · Familiaridade digital ______
· Experiência com o sistema ______ · Data ______

| Tarefa | Resultado | Tempo (mm:ss) | Ajuda recebida | Erros e criticidade | Observações |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
