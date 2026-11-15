# Serviços financeiros: transações e concorrência

Referência dos serviços implementados. Requer o schema financeiro `d93a7e2f610c`;
inclusão de serviços requer também `e14a29bc7031`. Contratos públicos em
[financeiro HTTP](financeiro-mvp-http.md). Não autoriza migrações.

## Contrato dos serviços

Em `backend/app/services/financeiro.py`:

- `consultar_situacao(comanda_id, db, usuario, filial_id=None)`: retorna total dos
  itens, situação, recebimentos, estornos, líquido e saldo. Para legado sem
  controle, situação `nao_verificado`, com valores financeiros e saldo nulos.
  O total dos itens pode ser conhecido, mas não constitui cobrança do legado.
- `registrar_pagamento`: somente replay histórico com chave e payload originais;
  novos recebimentos avulsos são recusados.
- `registrar_estorno`: exige ADMIN, pagamento da mesma comanda/filial, Decimal
  positivo, motivo não vazio, timestamp com timezone e UUID de idempotência.
  Estorno não pode anteceder seu recebimento nem ultrapassar o restante do original.
- `fechar_comanda`: exige quitação real, UUID de idempotência e motivo para total
  zero. Recebe de zero a 16 pagamentos confirmados cuja soma deve quitar o saldo;
  grava-os e fecha no mesmo commit. Não recebe total/saldo do cliente, não permite
  fiado ou novos pagamentos parciais. O fechamento é explícito e definitivo.

Todos retornam dataclasses imutáveis sem dependência de sessão após a operação.
Não há função de consulta agregada/global nem ampliação da leitura do chefe.
Recebimentos e estornos originais nunca são alterados ou excluídos.

## Autorização e isolamento

Releitura do usuário ativo, com lock compartilhado; reutilização da política
`autorizar_recebimento_ou_fechamento` e de `filiais.resolver_filial` com locks de
empresa/filial/vínculo. O escopo usa `escrita=True` também para consultas
financeiras: BARBEIRO_CHEFE não herda a leitura global da agenda. Barbeiros e
chefes só consultam/operam suas próprias comandas; ADMIN/RECEPCAO operam dentro
das filiais autorizadas pelo mecanismo existente. ADMIN mantém o escopo atual
de filiais/empresa ativas; não foi inventada uma regra nova de membership ADMIN.

Autorizar antes de revelar qualquer resultado idempotente. Ausência, outra
filial, outro profissional e filial informada divergente usam o mesmo erro de
recurso não encontrado. Usuário inativo/perfil sem acesso e estorno não ADMIN
são negados. Mudanças de atividade/vínculo aguardam os locks compartilhados;
se revogação confirmar primeiro, a operação revalida e falha.

## Transações, saldo e locks

Sessão PostgreSQL READ COMMITTED obrigatória. Reutiliza `transacao_escrita`, que
participa da transação iniciada pela autenticação e faz um único commit, com
rollback e classificação segura das falhas. Não usa begin aninhado, commits
intermediários ou retries automáticos. Exige sessão sem objetos novos, sujos ou
excluídos; rejeita sessão com alterações pendentes antes de descartá-las.

Ordem: usuário/contexto de autorização → agendamento FOR UPDATE → comanda FOR
UPDATE. Releitura com populate_existing impede uso de entidades anteriores à
espera do lock. Todos os escritores financeiros usam o mesmo protocolo; dois
operadores, mesmo com chaves diferentes, não calculam saldo em paralelo.

Total autoritativo = soma Decimal de quantidade × preço dos itens. O cache
`comandas.valor_total` e os preços atuais do catálogo não entram no cálculo.
Quantidade/preço inválidos e total acima do limite monetário falham sem escrita.
Recebido líquido = soma dos pagamentos menos soma dos estornos da mesma comanda
e filial. Saldo negativo ou líquido negativo indicam inconsistência e bloqueiam
a operação. Snapshot de fechamento divergente também é recusado.

A inclusão em `app/services/itens_comanda.py` reutiliza o contexto e a ordem
usuário/contexto → agendamento FOR UPDATE → comanda FOR UPDATE. Depois bloqueia
o serviço do catálogo com FOR SHARE, estabilizando atividade e preço até o commit.
Não requer UPDATE/DELETE dos itens existentes. Só permite nova inclusão em comanda
aberta e verificada, sem alterar o agendamento ou os preços históricos.

Item e auditoria idempotente são gravados na mesma transação. O total retornado
é recalculado dos itens; o replay preserva o snapshot da operação, não reprecifica
nem reinsere. Se inclusão confirmar primeiro, fechamento valida o saldo já aumentado;
se fechamento confirmar primeiro, nova inclusão é recusada. SQL privilegiado que
ignore esse protocolo não é protegido pelos locks dos serviços.

A consulta financeira usa locks compartilhados de agendamento/comanda para
evitar mistura de snapshots enquanto calcula os agregados. Não faz DML ou
commit; o chamador deve encerrar a transação/fechar a sessão prontamente, inclusive
em erros. Consultar e escrever na mesma sessão depois disso é suportado quando
não há alterações pendentes; não manter essa transação aberta durante interação
do usuário ou chamadas externas.

## Idempotência e falhas

Chave UUID no escopo (comanda, operação). Fingerprint SHA-256 do payload validado
com nomes ordenados, Decimal canônico, UUID e instante UTC. Motivos são aparados.
Mesmo instante em outro offset e valores 10.0/10.00 são equivalentes. Operador
não integra o payload: outro operador ainda autorizado pode repetir a mesma
requisição sem gerar outro recebimento; o responsável original é preservado.

Mesma chave e conteúdo retornam o DTO original. Conteúdo diferente lança
`ConflitoIdempotenciaFinanceira`, sem escrita. Fechamento só pode existir uma
vez: outra chave recebe estado incompatível. Repetição idêntica é resolvida
antes de conferir janela relativa/fechamento, inclusive para estorno executado
antes de um fechamento. Isso não permite novo estorno em comanda fechada.

O INSERT é flushed e recarregado antes do commit para capturar o carimbo real
do servidor. Uma falha nessa leitura ainda reverte a escrita. Não há SELECT
depois do commit. Timeout/desconexão que deixe confirmação indeterminada propaga
`ConfirmacaoIndeterminada` do padrão existente; repetir somente com a mesma
chave e conteúdo. Se o commit aconteceu, devolve o original; se não aconteceu,
executa uma vez após revalidar. Não continuar após IntegrityError em sessão
abortada nem transformar qualquer erro SQL em conflito de negócio.

As constraints UNIQUE permanecem como defesa adicional. Chaves diferentes
representam operações distintas: um segundo fechamento é bloqueado pelo estado
financeiro, mas duas inclusões do mesmo serviço com chaves diferentes não são
deduplicadas por semelhança. O cliente deve conservar a chave da intenção original.

## Datas e auditoria

Relógio de validação obtido do PostgreSQL (`clock_timestamp`) dentro da transação
após o lock, apresentado em America/Recife. Instantes comparados em UTC.
Sete dias = 168 horas contínuas, limite inclusivo. Data futura é recusada para
todos os perfis; além de sete dias só ADMIN. Reenvio idêntico não expira.

Recebimentos, estornos e fechamento exigem conclusão operacional; a inclusão de
serviços também pode ocorrer antes dela. Não se inventou
uma proibição de data efetiva anterior ao timestamp de conclusão: data do fato
econômico e momento de registrar são distintos. Estorno exige data não anterior
ao próprio recebimento e não futura; como só ADMIN pode estornar, não há limite
retroativo de sete dias para ele.

Schema existente comporta auditoria de operador, data efetiva, data de registro
imutável e chave/fingerprint. Pagamento não possui campo de justificativa textual
retroativa nem snapshot do perfil do operador. Caso esses campos sejam exigidos,
será necessária migração aditiva antes de aceitar esse novo contrato; não foram
embutidos em fingerprint ou em campos de outro significado. Motivo de estorno e
fechamento zero é persistido normalmente nas colunas existentes.

## Erros de domínio

`financeiro_errors.py` distingue entrada inválida, acesso negado, recurso não
encontrado, histórico não verificado, estado incompatível, saldo insuficiente,
limite de estorno excedido, conflito de idempotência e dados inconsistentes.
Não dependem de HTTP e não carregam mensagem do driver. A camada HTTP mapeia
explicitamente esses erros, mantendo 404 uniforme para escopo
oculto e preservando a distinção de resultado de commit desconhecido.

## Legado e próximos incrementos

Na etapa 3 não havia ativação automática. A etapa 4 passou a criar o controle
das novas comandas na transação de criação do agendamento; os serviços financeiros
continuam sem ativar ou conciliar registros. Ver [ativação e contratos HTTP](financeiro-mvp-http.md).

Fluxo de conciliação proposto, ainda não implementado: ADMIN identifica a comanda
legada, verifica comprovantes/fontes, registra evidências e classificação do
histórico e submete uma ativação explícita auditada. Recebimento antigo comprovado,
saldo inicial devido e ausência de evidência precisam de representações distintas.
Não simular pagamento para zerar saldo nem apenas criar controle e presumir dívida.
O desenho de saldo de abertura/evidências exige contrato e possivelmente migração
próprios antes de implementar essa conciliação.

## Integração e limites

Novas comandas recebem controle na transação de criação do agendamento.
Conclusão do atendimento mantém a comanda aberta. Fechamento integral atualiza
o estado/data operacional e grava o snapshot financeiro atomicamente. Registros
históricos não são modificados por consulta; a apresentação de quitação exige
comprovação financeira, conforme [interface](comandas-interface.md).

Histórico é lido do banco, sem lista otimista paralela. O frontend persiste
intenções em `sessionStorage` e bloqueia inclusão/fechamento enquanto há operação
incerta local; não há reserva distribuída por dispositivo no banco. Consultar
não substitui replay com a chave/payload originais. Não há reabertura ou conciliação
automática do legado.

Os testes ficam em `backend/tests` e `backend/integration_tests`, incluindo
`test_financeiro_servicos.py`, `test_financeiro_historico.py`,
`test_fechamento_integral.py` e `test_itens_comanda.py`. Testes PostgreSQL exigem
destino descartável validado pelo conftest, sem banco externo; falhas e resultados
de execução devem permanecer em `.local-qa/`, sem versionamento.
