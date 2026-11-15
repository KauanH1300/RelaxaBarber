# Etapa 3 — homologação integrada isolada

## Resultado

**Aprovado no ambiente descartável**, com React/Vite, Firefox, FastAPI/Uvicorn,
JWT real, serviços reais e PostgreSQL 17. Nenhuma correção no código da aplicação
foi necessária. Não foi iniciada a reformulação visual.

Branch preservada: `feat/comandas-fechamento-integral-atomico`.
Lidos os relatórios das etapas 1, 2 e 3 antes da execução.

## Preservação

Snapshot byte a byte dos 61 arquivos anteriormente modificados/não rastreados,
com manifesto SHA256, em:
`C:\Users\kauan\AppData\Local\Temp\relaxabarber-homologacao-20261114-233044`.
Ao final, os 61 arquivos continuaram idênticos ao snapshot. Nenhuma nova branch,
stash, commit, push, reset, clean ou substituição de trabalho local.

Adicionados nesta homologação:

- `backend/integration_tests/homologacao_etapa3.py`: provisionamento opt-in da
  base descartável e fixtures históricas explícitas, com validação do destino.
- `frontend/tests/homologacao-etapa3.browser.mjs`: fluxo real no Firefox,
  incluindo proxy de transporte para provocar timeout/503 sem simular sucesso financeiro.
- Este relatório e os arquivos de evidência em `docs/qa-etapa3-isolada/`.

Nenhum arquivo preexistente de frontend/backend foi editado nesta homologação.

## Isolamento comprovado antes das escritas

PostgreSQL exclusivo `rb-homolog-pg`, criado com:

```text
docker run -d --name rb-homolog-pg --network none
  --tmpfs /var/lib/postgresql/data:rw
  -e POSTGRES_USER=rb_concorrencia_test
  -e POSTGRES_DB=relaxabarber_concorrencia_test
  -e POSTGRES_HOST_AUTH_METHOD=trust
  postgres:17 postgres -p 55432 -c listen_addresses=127.0.0.1
```

O bloco acima apresenta os argumentos em múltiplas linhas para leitura;
no PowerShell foram enviados como uma única linha. Não há porta publicada,
IP externo, gateway ou volume persistente. `trust` vale somente nesse namespace
sem saída e sem portas publicadas; não é configuração de aplicação/produção.

Executores `rb-homolog-tests`, `rb-homolog-api` e `rb-homolog-browser` usaram
`--network container:rb-homolog-pg`. Foram montados arquivos de código/teste
selecionados, somente leitura, sem `.env` do backend ou credenciais reais.
Não foi utilizado o Compose habitual, que carrega o `.env`.

Antes de provisionar, comprovados identidade SQL, ausência de `.env` e erro
101 (rede inacessível) na conexão externa a `1.1.1.1:443`.

```text
Provisionamento/testes:
postgresql+psycopg2://rb_concorrencia_test@127.0.0.1:55432/relaxabarber_concorrencia_test

Processo Uvicorn (DATABASE_URL explícita, diferente da conexão de provisionamento):
postgresql+psycopg2://relaxabarber_dev_app@127.0.0.1:55432/relaxabarber_concorrencia_test

PYTHONPATH=/source:/source/integration_tests
RB_HOMOLOG_ISOLADO=descartavel-sem-rede
SECRET_KEY=chave-ficticia-exclusiva-homologacao-descartavel
```

O login efetivo `relaxabarber_dev_app` não é superusuário e não possui bypass RLS.
Os grants do runtime são os do helper existente de integração, sem ampliar
permissões financeiras. Uvicorn escutou `127.0.0.1:8001`; Vite em
`127.0.0.1:5173`, com `VITE_API_URL=http://127.0.0.1:8000` para o proxy local.
Todos compartilham exclusivamente o loopback isolado.

A cadeia **existente** de migrations foi aplicada apenas na base temporária
por fixtures, para reproduzir constraints/locks/grants reais. Nenhuma nova
migration criada, nenhuma migration/operação no Supabase. Nenhum script de
QA remoto ou `*.supabase.mjs` executado.

## Cenários reais aprovados

| Cenário | Evidência observada |
| --- | --- |
| Criar agendamento, registrar chegada, iniciar e concluir | POST/PATCH reais; concluído mantém comanda aberta e data de fechamento nula |
| Ciclo inteiro pela interface | Criação no modal da agenda, três ações operacionais, consulta da comanda e pagamento pelo formulário React; todas as escritas pela UI |
| Integral em um método | PIX, crédito e débito exercitados pelo formulário, conforme o perfil |
| Composição R$ 100 PIX + R$ 200 dinheiro | Um POST, dois pagamentos, total/líquido R$ 300, saldo zero e fechamento automático |
| Insuficiente R$ 100 para R$ 300 | UI bloqueia; POST direto retorna 409; zero pagamentos persistidos e comanda aberta |
| Clique duplo | Dois cliques síncronos produzem um único POST no cenário combinado |
| Replay | Mesma chave/payload retorna 200, sem novos recebimentos |
| Detalhes/indicadores | Após POST, nova consulta automática; detalhe passa a Fechada e contador de abertas passa a zero, sem reload manual |
| ADMIN e RECEPCAO | Fechamento autorizado de comanda de profissional da filial |
| BARBEIRO e BARBEIRO_CHEFE | Fechamento próprio autorizado; leitura/escrita financeira de outro profissional retornam 404 e não persistem |
| Filial incorreta | 404 nos quatro perfis; ID real não pode ser consultado sob outro contexto de filial |
| Quitação histórica verificada | Lista vazia; permanece um único pagamento anterior; data operacional histórica preservada |
| Legado não verificado | UI sem formulário de recebimento, líquido desconhecido; tentativa direta de fechar retorna 409; sem controle/pagamento/fechamento criados |
| Timeout após commit | Proxy recebe resposta real 200 e atrasa 17 s; Axios expira em 15 s; consulta comprova pagamento já persistido; recuperação usa chave/payload idênticos e mantém um pagamento |
| 503 antes de encaminhar | Zero pagamentos antes de recuperar; mesma intenção confirma exatamente uma vez no FastAPI |

Os primeiros cenários usam HTTP real para preparar agendamentos e a UI para os
recebimentos. O cenário final executa também criação e transições pela UI,
evitando que somente a preparação HTTP seja confundida com prova ponta a ponta.

O proxy não produz respostas financeiras de sucesso: encaminha dados ao FastAPI
real e só injeta atraso de resposta ou indisponibilidade de transporte.
As verificações posteriores consultam o FastAPI diretamente e, ao final, SQL.

## Testes e persistência

Regressão PostgreSQL, antes de preparar a massa do navegador:

```text
python -m pytest integration_tests/test_fechamento_integral.py
  integration_tests/test_financeiro_http.py
  integration_tests/test_comanda_estados.py -q -p no:cacheprovider
```

**80 aprovados em 77,37 s**, incluindo transações, rollback, idempotência,
concorrência com mesma/outra chave, autorização, filial, compatibilidade e locks.
O executor usa as dependências locais em mount somente leitura; não usa `.env`.

Homologação real:

```text
python integration_tests/homologacao_etapa3.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
node --experimental-websocket tests/homologacao-etapa3.browser.mjs
```

Esses comandos exigem o namespace, variáveis, mounts e login restrito descritos
acima; o provisionamento é destrutivo exclusivamente para a base descartável.
Não executar como atalho em um backend habitual. O frontend foi copiado para
`/app` efêmero dentro do container; o checkout permanece somente leitura.

Checks finais sem rede, em container separado:

```text
node /source/tests/helpers/validarFrontend.cjs
```

**126 testes frontend aprovados**, TypeScript, ESLint e Vite build com exit 0.
`git diff --check` aprovado. Nenhum teste desativado para obter aprovação.

Persistência final: 11 comandas fictícias, 10 controles, 9 pagamentos e
8 fechamentos financeiros. Dos 9 pagamentos, um é a fixture histórica quitada;
os outros oito correspondem a sete novas comandas, uma delas com dois métodos.
As duas comandas dos testes de acesso indevido permanecem abertas, sem pagamento
nem data de fechamento. O legado não verificado preserva o estado/data históricos
e permanece sem comprovação financeira.

Dez POSTs saíram da UI: sete intenções de fechamento novo e uma finalização
de quitação histórica, com dois reenvios de recuperação. Uma tentativa
interceptada com 503 não alcançou o backend. O replay HTTP adicional foi
verificado separadamente.

## Erros encontrados e correções de teste

- O provisionador inicial importava um helper que depende de pytest, ausente
  na imagem da aplicação. Substituído por fixtures SQL locais explícitas.
- Corrigido acesso a atributos ORM expirados após encerrar a sessão de seed.
- E-mails fictícios em `.test` permitiam login, mas o schema `EmailStr` de saída
  rejeitava `/auth/me` com 500. Trocados exclusivamente os dados de teste para
  `homolog.example.com`, sem mudar validação ou autenticação da aplicação.
- O teste de timeout observava o aviso de pendência, exibido durante o envio,
  antes do término da operação. Corrigido para aguardar o timeout e a consulta
  posterior (`aria-busy=false`) antes de verificar persistência/replay.

Após esses ajustes, a suíte inteira passou; foi repetida com o cenário adicional
da agenda e a verificação de preservação de data histórica. Nenhum defeito de
integração da aplicação foi identificado nos cenários executados.

As tentativas anteriores foram preservadas como diagnóstico, identificadas por
`tentativa*.json`; não são o resultado final. `homologacao.json` é a execução
final aprovada. `diagnostico-tentativa4.*` mostra a falha de sincronização do teste,
não um erro financeiro da aplicação.

## Evidências e limites

- `qa-etapa3-isolada/homologacao.json`: cenários, IDs fictícios e resultado final.
- `qa-etapa3-isolada/fechamento-combinado.png`: diálogo real fechado e indicadores atualizados.
- `qa-etapa3-isolada/identidade-e-contagens.json` e `persistencia-final.txt`: SQL final com login restrito.
- `qa-etapa3-isolada/isolamento-*.txt` e `prova-sem-env-sem-saida.txt`: namespace, mounts e ausência de acesso externo.
- `qa-etapa3-isolada/postgresql-testes.txt` e `frontend-checks.txt`: resultados dos executores.
- `qa-etapa3-isolada/seed-ficticio.json`: identificação da massa temporária; não contém tokens/credenciais reais.

Confirmação de pagamento continua sendo declaração do operador, sem gateway
bancário. A recuperação continua vinculada à aba/sessionStorage. Estorno novo
após fechamento permanece bloqueado pela regra existente, coberta pela regressão
PostgreSQL; não foi criada reabertura. A homologação não autoriza reclassificar
dados históricos reais nem equivale a auditoria de toda a base de produção.

Próximo passo: revisão desta evidência pelo responsável antes de iniciar a
reformulação visual. Sem alterações no design Stitch, commit ou push.

Ao terminar, removidos `rb-homolog-browser`, `rb-homolog-api`,
`rb-homolog-tests`, `rb-homolog-pg` e a tag da imagem derivada
`relaxabarber-homolog-browser:latest`. A base em tmpfs foi descartada.
Os containers preexistentes `relaxabarber-backend-1` e
`relaxabarber-frontend-1` continuaram em execução, sem intervenção.
