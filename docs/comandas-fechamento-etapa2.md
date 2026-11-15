# Etapa 2 — recebimento integral e fechamento atômico

> Documento histórico de implementação, mantido para revisão; descrições e
> pendências abaixo refletem sua etapa, não o estado atual do sistema.
> Referências técnicas atuais: [interface](comandas-interface.md),
> [contratos HTTP](financeiro-mvp-http.md), [transações](financeiro-mvp-servicos.md)
> e [persistência](financeiro-mvp-persistencia.md).
> Evidências de execução são locais e não integram a documentação versionada.


## Base e preservação

Branch mantida: `feat/comandas-fechamento-integral-atomico`. Antes de editar,
os 54 arquivos modificados/não rastreados foram copiados com SHA256 para
`C:\Users\kauan\AppData\Local\Temp\relaxabarber-etapa2-20261114-181639`.
Nenhum commit, stash, push, reset, clean ou nova branch. Nenhum arquivo de
frontend foi alterado nesta etapa. O snapshot temporário não substitui backup
durável nem commit.

## Compatibilidade histórica confirmada

As decisões de `comandas-fechamento-etapa1.md` foram mantidas:

- Conclusão do atendimento não fecha a comanda nem preenche data de fechamento.
- Status operacional histórico `fechada` isolado não comprova quitação.
- Sem controle financeiro explícito, a situação continua `nao_verificado`:
  somatórios desconhecidos, sem cobrança, ativação ou conciliação automática.
- Lançamentos e estornos existentes são preservados. O restante é calculado
  pelos itens menos o recebido líquido (pagamentos menos estornos), sob lock.
- Comanda histórica já marcada fechada mantém a data operacional antiga.
  O novo registro financeiro tem sua própria data e auditoria. Comanda aberta
  recebe estado/data de fechamento na mesma transação do fechamento financeiro.
- Consulta e replay não reclassificam registros nem corrigem datas antigas.
- Quitação verificada anterior pode ser finalizada sem inserir outro pagamento.

Não foi criada ou executada migração de aplicação, nem acessado o Supabase.
Somente a cadeia existente de migrações foi aplicada pelos fixtures do banco
descartável explicitamente autorizado para testes.

## Prova de isolamento antes de qualquer teste com escrita

PostgreSQL 17, container exclusivo `rb-atomico-pg`:

```text
--network none
--tmpfs /var/lib/postgresql/data:rw
POSTGRES_USER=rb_concorrencia_test
POSTGRES_DB=relaxabarber_concorrencia_test
POSTGRES_HOST_AUTH_METHOD=trust
postgres -p 55432 -c listen_addresses=127.0.0.1
```

Não há porta publicada, IP, gateway ou volume de produção. A autenticação trust
é exclusiva desse namespace de rede sem saída, com dados em tmpfs.
O executor `rb-atomico-tests` usa `--network container:rb-atomico-pg`; compartilha
somente esse loopback e não a rede dos containers da aplicação.

Os mounts de código são somente leitura e selecionados: app, alembic, tests,
integration_tests, pytest.ini e as dependências locais em `/deps`. Não são
montados `.env`, diretório da aplicação completo ou credenciais de produção.
A execução usa cópias efêmeras desses arquivos dentro do container.

Configuração exclusiva:

```text
RELAXABARBER_TEST_DATABASE_URL=postgresql+psycopg2://rb_concorrencia_test@127.0.0.1:55432/relaxabarber_concorrencia_test
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=/deps:/tmp/rb-etapa2
```

Antes de executar testes foram comprovados: ausência de `.env` e `DATABASE_URL`,
conexão externa recusada pelo namespace, e identidade SQL exata:
`relaxabarber_concorrencia_test`, `rb_concorrencia_test`, `127.0.0.1`, `55432`.
O conftest exige destino, porta, usuário e banco fixos; valida a identidade antes
de provisionar papéis ou aplicar migrations. Não usar essa suíte em outro banco.

## Contrato HTTP

### POST /comandas/{id}/fechamento-financeiro

Autenticação e escopo de filial permanecem. Header `Idempotency-Key` obrigatório
(UUID), persistido pelo cliente antes do envio. Exemplo de corpo:

```json
{
  "pagamentos": [
    {"valor":"10.01","forma":"pix","recebido_em":"2026-11-14T13:00:00-03:00","confirmado":true},
    {"valor":"20.49","forma":"debito","recebido_em":"2026-11-14T13:00:00-03:00","confirmado":true}
  ],
  "motivo": null
}
```

- Lista de zero a 16 parcelas, cada uma positiva, decimal textual exata, sem
  fração de centavo. Formas existentes: dinheiro, pix, debito e credito.
- `confirmado` é obrigatório e deve ser o booleano `true`; false, ausência,
  null, string e número são rejeitados. O serviço revalida também chamadas diretas.
- Essa confirmação é declaração do operador autorizado, como no modelo atual
  de recebimentos. Não há gateway/conciliação bancária automática no projeto.
  Não é prova independente emitida por Pix ou adquirente.
- Atendimento deve estar concluído e histórico financeiro verificado.
- Soma exata do restante sob lock; insuficiência e excesso retornam 409.
- Mantidas as regras de timezone, futuro e retroatividade (168 horas inclusivas
  para não ADMIN), baseadas no relógio do banco.
- `{}` ou `{"pagamentos":[]}` apenas finaliza saldo já zero. Total zero mantém
  exigência de motivo auditável e não cria recebimentos de valor zero.
- Resposta 200 mantém `FechamentoFinanceiroOut`: comanda, filial, total,
  recebido_liquido, motivo, registrado_em, registrado_por e chave_idempotencia.
  O GET financeiro continua fornecendo resumo e histórico persistido.
- Reenvio após timeout deve repetir chave, lista, ordem, formas, valores,
  datas e motivo originais. Representações equivalentes de Decimal/data são
  canônicas. Outra composição com a mesma chave retorna conflito 409.
- Outra chave em comanda já financeiramente fechada retorna 409 sem cobrança.
- Códigos de autenticação, autorização, recurso, entrada e persistência mantidos.

### POST /comandas/{id}/pagamentos

Deprecado no OpenAPI. Mantém entrada/resposta antigas **somente para replay**
de pagamento existente com chave/payload originais. Novos lançamentos avulsos,
parciais ou integrais, retornam 409 `estado_financeiro_incompativel` sem escrita.
Chave existente com outro conteúdo retorna 409 `conflito_idempotencia`.
Autorização é revalidada antes de recuperar o lançamento.

O GET financeiro e o POST de estorno mantêm seus contratos.

## Transação, concorrência e auditoria

O serviço reutiliza READ COMMITTED, sessão limpa, autorização atual, filial e
locks na ordem usuário/vínculos/contexto, agendamento e comanda. Todos os
recebimentos, o fechamento e a mudança de estado/data usam **um commit**.
Não há chamada de serviço que confirme parcela separadamente.

O fingerprint do fechamento inclui os fingerprints canônicos de todas as
parcelas em ordem. Para cada pagamento, a chave é derivada por UUIDv5 da chave
da operação e de `comanda_id:índice`. Assim, os registros existentes bastam para
auditoria e replay; não foi necessária nova tabela/coluna. Uma colisão com chave
histórica aborta toda a operação, inclusive parcelas já inseridas.

Fechamento sem novos pagamentos preserva o fingerprint antigo, permitindo
recuperar fechamentos anteriores. Replay não revalida janela relativa de data,
mas sempre revalida autenticação, atividade, vínculo, filial e autorização.
Falhas antes do commit revertem o conjunto. Confirmação indeterminada mantém
o contrato 503 existente: consultar e repetir a mesma operação, sem nova chave.

## Estornos e consequência preservada

Estorno novo continua exclusivo ADMIN e proibido após fechamento financeiro.
Como recebimento novo e fechamento agora são simultâneos, nenhum novo estorno
desses pagamentos fica disponível pelo fluxo atual após sucesso. Históricos
verificados ainda abertos continuam permitindo estornos conforme as regras
anteriores. Replay de estorno já registrado permanece possível com autorização.
Não foi criada reabertura, exclusão ou edição de histórico financeiro.

## Interface e pendências

Não houve alteração de frontend ou adoção do Stitch. O formulário antigo de
pagamento avulso passa a receber 409; o fechamento sem novos pagamentos ainda
funciona para quitações anteriores. A próxima etapa deve adaptar o formulário
para persistir e enviar a lista integral como uma única pendência/idempotência.
Não publicar backend e interface antiga como fluxo completo de operação.

Pendências antigas de sessionStorage não são apagadas automaticamente: se o
pagamento antigo já existia, o replay o recupera; se nunca foi confirmado, uma
nova tentativa avulsa é rejeitada e exige revisão antes de iniciar outra operação.
Não foi simulada proteção nova de clique no navegador: a proteção backend é
validada por replay e requisições concorrentes; a interface atual já possui trava
de envio e persistência da operação antiga, cuja adaptação fica para próxima etapa.

## Testes

Antes da Etapa 2: **225 casos PostgreSQL aprovados** (222 existentes + 3 novos de
estados, datas históricas, login restrito e locks). Sem correção na Etapa 1.

As suítes de serviços, HTTP e histórico foram adaptadas: preparações de pagamentos
anteriores usam fixtures explícitas, nunca um endpoint que permite criar parcial.
Regras de permissões, filial, estorno, rollback, replay e concorrência continuam
exercitadas pelos serviços reais. O cenário antigo de duas parciais concorrentes
foi substituído por rejeição de parcial e concorrência da operação integral.

Resultados finais:

| Execução | Resultado |
| --- | --- |
| PostgreSQL antes da Etapa 2, sete suítes pertinentes à Etapa 1 | 222 aprovados, 287,09 s |
| Novos estados/compatibilidade/locks, antes da Etapa 2 | 3 aprovados, 6,64 s |
| PostgreSQL após implementação: integral, serviços, HTTP, histórico, ativação, estados | 175 aprovados, 212,74 s |
| Suíte backend existente, mocks/SQLite em memória | 843 aprovados e uma falha de preparação: faltava alembic.ini no executor |
| Segurança após incluir alembic.ini, sem .env | 15 aprovados, 26,38 s; inclui o único teste que falhou |
| Novos contratos/validação integral | 23 aprovados, 30,45 s |
| git diff --check | Aprovado |

Total backend sem banco externo: **867 casos distintos aprovados**, combinando
844 casos existentes (incluindo a correção da preparação/reexecução) e 23 novos.
As contagens de integração antes/depois se sobrepõem e não devem ser somadas
como casos distintos. Não houve teste desativado ou marcado xfail/skip para
contornar a nova regra. Não foi necessário alterar código por falha de integração.

O único ajuste de ambiente foi copiar `backend/alembic.ini` para a cópia
descartável, sem montar `.env`. O teste de CLI usa dialect propositalmente
inexistente e falha antes de conectar; não executa migração. A suíte de segurança
completa foi repetida e passou.

Comandos executados dentro do executor, processos separados:

```text
python -m pytest integration_tests/test_financeiro_ativacao.py integration_tests/test_cancelamento_etapa_g.py integration_tests/test_concorrencia.py integration_tests/test_financeiro_servicos.py integration_tests/test_financeiro_http.py integration_tests/test_financeiro_historico.py integration_tests/test_financeiro_persistencia.py -q -p no:cacheprovider
python -m pytest integration_tests/test_comanda_estados.py -q -p no:cacheprovider
python -m pytest integration_tests/test_fechamento_integral.py integration_tests/test_financeiro_servicos.py integration_tests/test_financeiro_http.py integration_tests/test_financeiro_historico.py integration_tests/test_financeiro_ativacao.py integration_tests/test_comanda_estados.py -q -p no:cacheprovider
python -m pytest tests -q -p no:cacheprovider
python -m pytest tests/contracts/test_fechamento_integral.py -q -p no:cacheprovider
python -m pytest tests/security/test_segredos.py -q -p no:cacheprovider
```

O baseline foi executado antes de alterar o código de aplicação. Os 175 casos
posteriores cobrem divisão em métodos, regularização líquida de histórico,
valores inválidos/não confirmados, saldo incorreto, falta de confirmação,
rollback no segundo pagamento/no fechamento/na atualização de estado/no commit,
confirmação indeterminada antes/depois de commit, colisão de chave histórica,
concorrência com mesma/outra chave e payload divergente, locks, revogação,
isolamento por filial, login restrito e bloqueio de novos estornos após fechamento.

## Arquivos desta etapa

Modificados sobre o estado local anterior:

- `backend/app/api/routes/financeiro.py`: contrato/documentação e depreciação do avulso.
- `backend/app/schemas/financeiro.py`: lista limitada e confirmação estrita.
- `backend/app/services/financeiro.py`: transação integral, fingerprint de lote,
  chaves de parcelas e recuperação histórica sem nova escrita avulsa.
- `backend/integration_tests/test_financeiro_ativacao.py`: conclusão sem fechamento
  e uso da operação integral após conclusão real.
- `backend/integration_tests/test_financeiro_servicos.py`: transações, permissões,
  datas, locks, concorrência e fixtures de histórico adaptados ao novo contrato.
- `backend/integration_tests/test_financeiro_http.py`: novo corpo integral e replay
  do endpoint antigo, sem perder cenários de segurança/estorno.
- `backend/integration_tests/test_financeiro_historico.py`: preparações históricas
  explícitas e quitação/recuperação pelo fechamento integral.
- `backend/tests/persistence/test_estados_comanda.py`: quitações anteriores
  preparadas como fixtures, sem usar avulso proibido para criar dados.
- `docs/financeiro-mvp-http.md`: aponta para o contrato atual.

Criados:

- `backend/integration_tests/test_comanda_estados.py`: três provas PostgreSQL da Etapa 1.
- `backend/integration_tests/test_fechamento_integral.py`: integração da operação integral.
- `backend/tests/contracts/test_fechamento_integral.py`: 23 contratos/validações novos.
- Este relatório.

SHA256 dos 54 arquivos anteriores: 45 permaneceram byte a byte idênticos;
os nove acima receberam os ajustes listados. Todo o frontend e os demais
documentos, scripts e evidências anteriores foram preservados.

Ao finalizar, os containers exclusivos `rb-atomico-tests` e `rb-atomico-pg`
foram removidos. Os dois containers preexistentes da aplicação continuaram
em execução. O PostgreSQL descartável não foi deixado ativo. Sem commit/push.
