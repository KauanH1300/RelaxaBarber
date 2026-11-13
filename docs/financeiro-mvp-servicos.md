# Etapa 3: serviços financeiros transacionais

Implementação sem endpoints, frontend, ativação de controle financeiro ou
conciliação de legado. Nenhuma migração foi criada/alterada nesta etapa e nenhuma
conexão com Supabase foi utilizada. Requer o schema d93a7e2f610c quando for
implantado futuramente mediante autorização própria.

## Contrato dos serviços

Em `backend/app/services/financeiro.py`:

- `consultar_situacao(comanda_id, db, usuario, filial_id=None)`: retorna total dos
  itens, situação, recebimentos, estornos, líquido e saldo. Para legado sem
  controle, situação `nao_verificado`, com valores financeiros e saldo nulos.
  O total dos itens pode ser conhecido, mas não constitui cobrança do legado.
- `registrar_pagamento`: exige Decimal positivo, forma dinheiro/pix/debito/credito,
  timestamp com timezone, UUID de idempotência e comanda concluída/verificada.
- `registrar_estorno`: exige ADMIN, pagamento da mesma comanda/filial, Decimal
  positivo, motivo não vazio, timestamp com timezone e UUID de idempotência.
  Estorno não pode anteceder seu recebimento nem ultrapassar o restante do original.
- `fechar_comanda`: exige quitação real, UUID de idempotência e motivo para total
  zero. Não recebe total/saldo do cliente. O fechamento é explícito e definitivo.

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

O runtime existente não possui UPDATE/DELETE de itens. Ler itens com FOR SHARE
exigiria privilégio UPDATE; a implementação final não usa esse lock adicional
nem amplia grants. Atualmente o único escritor de itens é a criação atômica
do agendamento/comanda, antes de expor o registro. Qualquer futura edição,
remoção ou inclusão de itens deve bloquear o mesmo pai e impedir mudanças após
recebimentos. SQL privilegiado que ignore esse protocolo não está protegido
pelos serviços; proteção global contra esse bypass exigiria desenho/migração
próprios, não realizados nesta etapa.

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

As constraints UNIQUE permanecem como defesa adicional. Chaves diferentes não
identificam um erro humano de lançamento duplicado se ambos os valores ainda
couberem no saldo; não se bloqueiam pagamentos legítimos por heurística de valor.

## Datas e auditoria

Relógio de validação obtido do PostgreSQL (`clock_timestamp`) dentro da transação
após o lock, apresentado em America/Recife. Instantes comparados em UTC.
Sete dias = 168 horas contínuas, limite inclusivo. Data futura é recusada para
todos os perfis; além de sete dias só ADMIN. Reenvio idêntico não expira.

Registro é realizado apenas depois da conclusão operacional. Não se inventou
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
Não dependem de HTTP e não carregam mensagem do driver. A etapa de endpoints
deverá mapear explicitamente esses erros, mantendo 404 uniforme para escopo
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

A etapa 5 expõe os serviços por schemas Pydantic e quatro endpoints FastAPI,
sem mudar as regras ou a fronteira transacional deste módulo. Ver os contratos,
erros e evidências em [financeiro HTTP](financeiro-mvp-http.md).
Conciliação de legado e frontend continuam para etapas futuras.
Implantação da migração remota continua pendente de autorização e planejamento
de recuperação, especialmente porque o banco informado não possui backup automático.

## Validação desta etapa

- Suíte backend completa: 766 testes aprovados, incluindo 36 novos testes puros.
- PostgreSQL de serviços: 73 aprovados na execução final, incluindo timeout real
  de lock, falha de leitura pré-commit, commit abortado e confirmação indeterminada.
- PostgreSQL de persistência: 51 aprovados na regressão conjunta com os serviços.
  São 124 cenários PostgreSQL distintos aprovados ao todo, sem contar reexecuções.
- Concorrência determinística com conexões independentes e comprovação de espera
  por lock: operadores/chaves iguais e diferentes, parcial/excedente, estornos
  concorrentes, estorno × fechamento nas duas ordens, fechamentos concorrentes e
  revogação concorrente antes/depois do pagamento.
- Contexto fictício com login PostgreSQL restrito também aprovado sem ampliar
  grants. A primeira execução revelou FOR SHARE desnecessário nos itens; foi
  removido e o fluxo completo passou com os privilégios já existentes.
- PostgreSQL 17 em container network none, sem portas publicadas, dados em tmpfs;
  executor compartilha apenas o loopback isolado via network container. Backend
  montado somente leitura, .env não carregado, credenciais exclusivamente fictícias.
  Suíte sem PostgreSQL executada em outro container network none.
- Nenhuma migração remota, endpoint, alteração de .env/DATABASE_URL, commit ou
  push. Os hashes de package.json e logo.png permaneceram iguais aos iniciais.
