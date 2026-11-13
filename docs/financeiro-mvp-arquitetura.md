# Financeiro MVP: proposta incremental

Status: proposta para aprovação. Somente a política pura de recebimento/fechamento
e seus testes foram implementados, sem ligação com rotas. Não há migração nova,
pagamento, fechamento financeiro ou mudança de comportamento operacional nesta etapa.

## Situação encontrada no código

- `services/agendamento.py` cria agendamento, serviços e comanda em uma transação.
  Os itens guardam descrição e preço do serviço no momento da contratação.
- O atendimento transita de pendente para aguardando/em_atendimento/cancelado;
  aguardando permite em_atendimento/cancelado; em_atendimento permite concluido.
  Concluido e cancelado são finais. Concluir grava comanda `fechada` e
  `data_fechamento`: representam fechamento **operacional**, sem prova de pagamento.
- `models/comanda.py` possui total armazenado, mas `schemas/comanda.py` calcula o
  total a partir dos itens. Já existem FK composta de contexto e uma comanda por
  agendamento. Não há modelo de pagamento nem endpoints de escrita de comanda.
- `routes/comandas.py` oferece GET da lista, painel e detalhe. O painel é
  operacional, usa a data do agendamento e declara pagamentos indisponíveis.
- A política de agenda concede leitura ampla ao BARBEIRO_CHEFE. Não reutilizar
  essa ampliação para relatórios financeiros. O frontend já distingue fechamento
  operacional de recebimento; preservá-lo até existir contrato financeiro.
- A persistência atual usa uma transação de escrita com commit único e distingue
  abortamento confirmado de confirmação indeterminada. Reutilizar esse tratamento.

## Modelo mínimo proposto

Separar três dimensões, evitando um único status ambíguo:

1. Operação: preservar inicialmente `status` e `data_fechamento` atuais.
2. Cobertura do histórico: `controle_financeiro_iniciado_em` nullable e responsável
   pela ativação/conciliação. NULL significa histórico não verificado, nunca pago
   ou dívida confirmada. Novas comandas passam a ter controle explícito.
3. Financeiro: aberto/fechado, com fechamento e eventual reabertura auditados.
   Derivar sem recebimento/parcial/quitado do saldo apenas sob controle financeiro.

`pagamentos_comanda`: UUID, comanda_id, filial_id, valor NUMERIC(10,2), forma
(`dinheiro`, `pix`, `debito`, `credito`), recebido_em TIMESTAMPTZ,
registrado_em TIMESTAMPTZ gerado pelo servidor, registrado_por FK de usuário,
chave_idempotencia UUID e fingerprint do payload normalizado. Preservar registros
com FK RESTRICT, sem exclusão em cascata. FK composta (comanda_id, filial_id)
referencia UNIQUE (id, filial_id) na comanda. Índices por comanda e por
(filial_id, recebido_em) para consultas financeiras autorizadas.

`eventos_financeiros_comanda`: UUID, comanda/filial com mesma FK composta, tipo
(ativação do controle, fechamento, reabertura), instante do servidor, responsável,
motivo e totais congelados no fechamento. Manter na comanda uma projeção
`fechada_financeiramente_em/por`, ambos nulos ou ambos preenchidos; gravar projeção
e evento na mesma transação. Não sobrescrever o fechamento operacional.

Estorno: lançamento separado imutável, referenciando pagamento original, valor
positivo, responsável, motivo, data efetiva e data de registro. Somatório estornado
não pode exceder o original. Correção = estorno auditado + novo recebimento;
nunca editar/apagar pagamento. Os perfis e o fluxo de reabertura dependem de
aprovação antes de implementar essa operação.

Não confundir registro manual de Pix/cartão com confirmação de liquidação por
instituição financeira. Integração de adquirentes/gateways fica fora deste MVP.

## Legado e migração proposta

Próxima revisão deve apontar para `c82f6a1d904b`, após conferir novamente o head.
Migração aditiva e transacional PostgreSQL, sem autocommit/DDL concorrente:

1. Preflight de metadados e agregados: itens negativos/quantidade inválida,
   totais fora da faixa, diferença entre total armazenado e soma de itens,
   integridade de contexto. Não corrigir dados automaticamente.
2. Adicionar campos nullable de controle/fechamento; todas as comandas existentes
   ficam com histórico não verificado, inclusive as atualmente `fechada`.
3. Criar tabelas, checks, FKs, índices, RLS e privilégios específicos na mesma
   transação. Conferir grants herdados/default privileges: não copiar permissões
   da Data API. Runtime sem UPDATE/DELETE de lançamentos imutáveis; projeções
   exigem privilégios separados. RLS não substitui autorização do backend;
   conexão postgres pode ignorá-la. Não alterar permissões globais do Supabase.
4. Não adicionar default que marque retroativamente o legado como verificado.
   Ativar novas comandas pelo backend no mesmo commit de criação; coordenar a
   disponibilização dessa versão para evitar novos registros sem controle.
5. Validar migração em PostgreSQL descartável com casos legados e rollback.
   Checks em tabelas antigas só após preflight/reconciliação aprovada; quando
   necessário, usar NOT VALID e VALIDATE posteriormente, sem ocultar pendências.

Legado fica fora de totais de recebimento e de cobrança automática. Conciliação
manual deve distinguir valor devido, recebimentos comprovados anteriores e saldo
de abertura, com evidência/responsável; nunca criar pagamentos fictícios para
fechar a conta. A política de ativação do legado precisa de aprovação.

Downgrade não pode apagar histórico financeiro: bloquear se houver lançamentos,
preferir correção progressiva. Implantação remota requer autorização própria e
plano de recuperação/backup verificado; esta proposta não executa implantação.

## Valores e invariantes

- Fonte autoritativa: soma de quantidade × preço unitário dos itens congelados,
  usando Decimal, nunca float. `valor_total` será cache compatível, não segunda
  fonte. Não recalcular pelo preço atual do catálogo nem alterar legado sozinho.
- Quantidade inteira > 0; preço >= 0; total <= 99.999.999,99; pagamento > 0 e
  <= 99.999.999,99; valores finitos. Validar escala de até dois decimais antes
  do INSERT: NUMERIC(10,2) pode arredondar silenciosamente. Checks também devem
  excluir NaN e valores fora da faixa. Limite agregado exige serviço transacional.
- Recebido líquido = pagamentos - estornos; saldo = total - recebido líquido.
  Situação financeira é calculada, não um booleano `pago` editável.
- Congelar alterações de itens após iniciar recebimentos; qualquer futura escrita
  de itens deve adquirir o mesmo lock da comanda. Não há esses endpoints hoje.
- Recebimento e fechamento exigem atendimento concluído e histórico verificado.
  Fechamento financeiro exige saldo exatamente zero e grava evento/projeção
  atomicamente. Recebimento que zera saldo não precisa fechar automaticamente.
  Excedentes, troco, total zero e automatização do fechamento aguardam aprovação.

## Transações, autorização e concorrência

Usar READ COMMITTED com locks explícitos e ordem compatível com os serviços
atuais: reler usuário ativo/autorizações, empresa/filial/vínculos, agendamento
FOR UPDATE e depois comanda FOR UPDATE, sempre com populate_existing. Validar
filial e profissional a partir dos registros persistidos, não do payload.
Não inverter essa ordem nos futuros serviços de pagamento, itens ou estorno.

ADMIN/RECEPCAO operam nas filiais autorizadas. BARBEIRO e BARBEIRO_CHEFE somente
nas próprias comandas, também com vínculo ativo. A política pura criada nesta
etapa verifica perfil/atividade/propriedade; o chamador futuro obrigatoriamente
aplica o isolamento por filial. Ela não autoriza consultar faturamento global.
Definir permissão de relatório separadamente; não expor agregados globais nas
respostas de recebimento nem reutilizar escopo amplo da agenda do chefe.

Dentro de um único commit: autorizar, bloquear, verificar idempotência, reler
estado/itens/saldo, validar valor e datas, inserir lançamento e eventual evento.
Todos os caminhos de escrita financeira usam o mesmo lock pai; isso serializa
recebimentos concorrentes mesmo com chaves diferentes. Somatórios e saldo não
podem ser garantidos por CHECK de uma linha. Para impedir bypass por SQL direto,
avaliar função de escrita controlada/trigger ou restringir rigorosamente o papel
de aplicação. Enquanto o backend usa postgres, locks no serviço não protegem
contra escritas externas privilegiadas.

UNIQUE (comanda_id, chave_idempotencia). Cliente gera e conserva chave antes de
enviar; mesma chave e mesmo payload retornam o lançamento original, inclusive
após fechamento. Mesma chave com payload diferente retorna conflito. Autorizar
sempre antes de consultar/devolver o resultado; não exigir estado aberto para
repetir uma operação já confirmada. Fingerprint inclui valor decimal canônico,
forma e data efetiva normalizada em UTC, sem credenciais ou dados pessoais.

Não capturar IntegrityError e continuar numa transação abortada: usar ON CONFLICT
adequado ou rollback e nova leitura autorizada. Em perda de resposta ao COMMIT,
reconsultar/repetir com a mesma chave, nunca gerar outra automaticamente.
Idempotência não detecta dois lançamentos humanos com chaves diferentes: propor
confirmação visual de duplicidade e futura referência externa quando disponível.
Não proibir dois pagamentos legítimos de mesmo valor/forma/data por heurística.

## Datas e decisões de negócio pendentes

Recebido_em representa o fato econômico, registrado_em o relógio do servidor;
aceitar apenas timestamps com fuso e apresentar no fuso da filial. Relatório
de recebimentos usa a data efetiva, relatório de auditoria usa registro, nunca
a data do agendamento como substituta.

Para aprovação, recomenda-se impedir datas futuras, permitir retroatividade curta
para recebimento próprio e janela maior supervisionada por ADMIN/RECEPCAO, com
motivo obrigatório e auditoria. Definir quantitativamente essas janelas, fuso de
referência e se a data efetiva pode anteceder a conclusão operacional. Nenhuma
dessas restrições foi implementada nem existe limite arbitrário em código.

Também decidir: ativação/conciliação do legado; excedente/troco (recomendação MVP:
registrar somente valor aplicado, rejeitar excedente); fechamento de total zero;
fechamento explícito ou automático; perfis/prazos para estorno e reabertura;
permissões de faturamento; retenção de comprovantes/referências externas. Até
aprovação, não criar endpoints nem tornar o fluxo financeiro disponível.

## Incrementos e testes seguintes

1. Aprovar decisões acima e nomes/contrato dos estados financeiros.
2. Implementar modelos e migração aditiva; testar upgrade com legado, constraints,
   RLS/grants e rollback exclusivamente em PostgreSQL descartável.
3. Serviços sem endpoints: parcial, múltiplas formas, saldo zero, retroatividade
   aprovada, autorização/revogação de vínculo, legado bloqueado, fechamento,
   reversão e trilha. Testar concorrência real em PostgreSQL e falha antes/depois
   de COMMIT, mesma chave concorrente e chaves diferentes disputando saldo.
4. Só depois adicionar contratos/endpoints e interface móvel em etapa própria.

Estoque: consumo e eventual devolução são eventos próprios, não consequência
automática de pagamento. Despesas: livro separado, não valores negativos em
recebimentos. Comissões: congelar base, percentual e beneficiário; aprovar regime
por serviço concluído ou recebimento, rateio de parciais e efeito de estornos.
Não calcular comissão histórica pelo percentual atual do catálogo.
