# Consulta de comandas

A página `/comandas` permite consultar itens e acompanhar o estado operacional
na filial ativa. O período inicial é o dia atual em America/Recife. Pesquisa,
profissional e datas são aplicados pelo botão **Aplicar filtros**; a aba de
status e a paginação fazem novas consultas no servidor. Apagar as duas datas
permite consultar todo o histórico autorizado.

## API de leitura

- `GET /comandas/painel`: `pagina` (inicial 1), `tamanho` (inicial 6, máximo 48),
  `busca` (até 100 caracteres), `status`, `profissional_id`, `data_inicio`,
  `data_fim`, `filial_id`.
- `GET /comandas/{uuid}`: detalhe com cliente, profissional, filial,
  atendimento e itens. Os campos anteriores continuam presentes.
- `GET /comandas`: listagem anterior preservada para compatibilidade.

A pesquisa procura nome do cliente ou trecho do UUID, com ou sem hífens.
Percentuais e sublinhados na pesquisa são literais. A identificação curta dos
cards é apenas visual; o UUID completo está no título acessível, no tooltip e
nos detalhes. Todas as operações usam o identificador completo.

As datas inicial e final são inclusivas e se referem à **data do atendimento**,
sem converter esse dia civil para UTC. Abertura e fechamento são instantes
formatados em America/Recife. A ordem da listagem é criação decrescente,
desempatada pelo UUID. A paginação usa limite e deslocamento no banco.

Os indicadores consideram pesquisa, profissional e período de todo o resultado,
antes do filtro de status e da paginação. Contagens não são multiplicadas pelos
itens. Valores são somados dos preços históricos dos itens, com `Decimal` no
backend; não são obtidos do total armazenado no cabeçalho.

## Permissões e significado dos valores

O contexto da filial é autorizado pelo backend em cada consulta. Barbeiro vê
somente suas comandas; chefe, recepção e administrador mantêm o escopo de
leitura existente nas filiais autorizadas. O filtro de profissional não amplia
esse acesso. O frontend descarta respostas de um contexto de filial anterior.

Status preservados: `pendente`, `aberta`, `fechada`, `cancelada`. O indicador
**Comandas abertas** conta apenas `aberta`, sem equiparar reserva pendente a
atendimento iniciado. **Valor em aberto** soma itens dessas comandas, sem
representar dívida comprovada ou faturamento recebido. **Fechadas no período**
usa a data do atendimento, não a data de pagamento.

O fechamento automático atual acompanha a conclusão do atendimento. **Não
comprova quitação.** Não existem registros de pagamento no domínio atual; o
indicador de pagamento fica indisponível. Na futura etapa de pagamentos será
necessário reconciliar essa regra com o fechamento por quitação previsto na
arquitetura original. Esta entrega não altera esse ciclo nem habilita cobrança,
edição de itens, impressão fiscal, comanda avulsa ou auditoria financeira.

## Validação local

Backend isolado, sem carregar banco externo:

```sh
cd backend
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider
```

Frontend:

```sh
cd frontend
node --test tests/*.test.mjs
npm run lint
npm run build
node tests/comandas.browser.mjs
```

O teste de navegador requer Node 22+ e Firefox instalado. Inicia frontend e API
fictícia em portas loopback temporárias, usa perfil descartável e encerra os
processos ao terminar. Não usa credenciais reais nem acessa o Supabase.
`FIREFOX_BIN` pode indicar o executável; `COMANDAS_SCREENSHOT_DIR` permite salvar
capturas em um diretório privado já existente fora do Git. As capturas usam
exclusivamente dados fictícios. A suíte PostgreSQL é separada e não deve ser
executada em banco persistente: suas fixtures recriam o schema.
