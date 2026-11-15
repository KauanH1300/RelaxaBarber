# Etapa 10 — interface financeira das comandas

> Documento histórico de implementação, mantido para revisão; descrições e
> pendências abaixo refletem sua etapa, não o estado atual do sistema.
> Referências técnicas atuais: [interface](comandas-interface.md),
> [contratos HTTP](financeiro-mvp-http.md), [transações](financeiro-mvp-servicos.md)
> e [persistência](financeiro-mvp-persistencia.md).
> Evidências de execução são locais e não integram a documentação versionada.


Implementação local na branch `feat/financeiro-comandas`, sem publicação ou operações remotas.

## Arquivos

Criados:

- `frontend/src/services/financeiro.ts`: contratos, transporte autenticado, valores em centavos, datas, escopo, mensagens sanitizadas e armazenamento de pendências.
- `frontend/src/pages/comandas/FinanceiroComanda.tsx`: consulta, formulários, revisão, confirmações e recuperação.
- `frontend/tests/financeiro.test.mjs`: sete testes de dinheiro, permissões, estados, datas, persistência, requisições e replay com mocks.
- `frontend/tests/helpers/validarFrontend.cjs`: executor dos checks offline na imagem Docker local, com checkout somente leitura.
- Este relatório.

Modificados:

- `frontend/src/pages/comandas/DetalheComanda.tsx`: integração financeira e inclusão dos campos de formulário no controle de foco do diálogo.
- `frontend/src/pages/comandas/Comandas.tsx`: orientação atualizada para acessar o financeiro pelos detalhes.
- `frontend/src/pages/comandas/Comandas.css`: estilos responsivos seguindo as cores existentes e foco visível.

## Comportamento

- Consulta o resumo financeiro autenticado com a filial da própria comanda. Exibe situação, total dos itens, recebimentos, estornos, recebido líquido e saldo retornados pelo backend.
- Mantém status operacional separado do financeiro. Legados apresentam valores desconhecidos como “Não verificado”, sem afirmar dívida, quitação ou habilitar novas movimentações.
- Pagamento parcial ou integral após comanda fechada e atendimento concluído; dinheiro, Pix, débito e crédito; valor positivo limitado ao saldo e prévia do saldo restante.
- Datas efetivas usam o fuso do dispositivo no formulário e são enviadas em UTC com timezone. Rejeita futuro e retroatividade superior a 168 horas para não ADMIN; estorno não antecede o pagamento original. O backend revalida os limites usando seu próprio relógio.
- Estorno somente ADMIN, com seleção de pagamento confirmado na montagem atual do painel, limite descontando os estornos conhecidos, motivo obrigatório e confirmação. O backend verifica o histórico completo sob lock.
- Fechamento explícito, separado da conclusão operacional, saldo zero e motivo obrigatório se o total for zero. Confirmação apresenta o resumo e informa o bloqueio de novas movimentações.
- ADMIN e RECEPCAO continuam no escopo de filial do cliente HTTP existente. BARBEIRO e BARBEIRO_CHEFE consultam somente suas próprias comandas; o painel não consulta financeiro global. Todas as requisições continuam sujeitas à autorização do backend.
- Erros 401/403/404 e erros financeiros recebem mensagens locais, sem exibir texto de driver ou dados de terceiros. Uma falha de consulta remove os dados financeiros visíveis.

## Idempotência e recuperação

Cada confirmação gera um UUID. Antes do envio, chave, operação e payload são persistidos em `sessionStorage`, sob chave por usuário, filial e comanda. Não são armazenados tokens, dados pessoais do cliente ou o histórico completo.

O botão usa trava síncrona e estado de carregamento para evitar cliques duplicados. Falha ao persistir impede o envio. Timeout, falhas 5xx, resposta descartada por mudança de contexto e conflito de idempotência preservam a pendência. Consultar o resumo não resolve automaticamente a operação: o usuário pode repetir o POST com a chave e payload originais, inclusive a data original. O replay continua possível após fechamento financeiro.

Um erro definitivo na primeira tentativa permite corrigir o formulário. Erros durante a recuperação de uma pendência anterior não apagam a intenção, pois não provam que a tentativa original deixou de gravar. Sucesso confirmado remove apenas a pendência com a mesma chave. Pendência corrompida bloqueia novos lançamentos.

O armazenamento sobrevive a recarregamentos na mesma aba. Não oferece recuperação garantida após fechar a aba, limpar o armazenamento ou mudar de dispositivo. A tela orienta manter a aba aberta até resolver o resultado. Não há coordenação entre abas para intenções diferentes.

## Bloqueio real do contrato

Os quatro endpoints existentes foram conferidos em `backend/app/api/routes/financeiro.py` e `backend/app/schemas/financeiro.py`. O GET retorna apenas somatórios, sem pagamentos, estornos ou fechamento individual. Não existe consulta de movimentações financeiras disponível nesses contratos.

Portanto, esta entrega **não conclui o requisito de histórico completo nem o estorno de pagamentos de sessões anteriores**. A interface identifica explicitamente que mostra apenas movimentações confirmadas na montagem atual do painel; não apresenta essa lista como histórico completo. Um ADMIN pode selecionar para estorno apenas pagamentos retornados pelos POSTs dessa montagem, inclusive replays recuperados.

Para concluir esses requisitos, é necessária uma consulta autorizada de pagamentos e estornos da comanda, incluindo os IDs e os dados necessários para determinar o limite restante de cada pagamento. O contrato deve manter a mesma ocultação de recurso e o mesmo escopo por filial/profissional. Não foi criado endpoint fictício nem modificado o backend nesta entrega.

## Validação

Execução em container descartável da imagem local `relaxabarber-frontend:latest`, com `--network none`, frontend montado somente leitura em `/source` e cópia de trabalho dentro do container. Nenhuma instalação de dependências.

- Testes existentes e novos: **117 aprovados**, incluindo **7 novos** financeiros.
- `tsc -b`: aprovado.
- `vite build`: aprovado.
- `eslint .`: aprovado.
- `git diff --check`: aprovado.

Os testes financeiros verificam centavos exatos; permissões próprias dos dois perfis de barbeiro; bloqueio de legado, estados operacionais e financeiro fechado; datas e retroatividade; separação e remoção seletiva de pendências; rejeição de payload temporário indevido; endpoints, payloads e headers de pagamento parcial/integral, estorno e fechamento; timeout após gravação simulada e replay sem duplicação; confirmação indeterminada e conflitos.

Não houve validação visual/interativa em navegador: a imagem disponível não contém Firefox. Os testes com mocks validam serviços e transporte; não substituem testes de interação dos formulários. Validação manual de responsividade, foco e fluxos completos de clique permanece pendente.

## Preservação

`frontend/package.json` e `frontend/src/assets/logo.png` já estavam modificados antes desta tarefa e foram preservados byte a byte. SHA256 antes/depois:

- package.json: `E3894A862473B3CC1E775E75F4D1333A92844A4D9376B13D7F40ACB4A4FB52B1`
- logo.png: `5744331DF85257A3E1D70A2B760C4C243A86DCA5DD2B3C62D1B1F2794CF8DF40`

Sem alterações de backend, migrations, schema, dependências, lockfiles, `.env` ou `DATABASE_URL`. Sem acesso ao Supabase, pagamentos reais, alterações de legados, criação/exclusão de dados remotos ou comandos Git de escrita.
