# Casos de Uso (UC) — RelaxaBarber

---

## UC01 — Autenticar Usuário

**Atores:** Proprietário, Barbeiro, Recepção.

**Pré-condições:** Usuário previamente cadastrado no sistema.

**Fluxo Principal:**
1. Usuário informa e-mail/usuário e senha.
2. Sistema valida credenciais.
3. Sistema redireciona para a interface correspondente ao perfil do usuário (RF24).

**Fluxos Alternativos:**
- **FA1 — Credenciais inválidas:** sistema exibe mensagem de erro e permite nova tentativa.
- **FA2 — Esqueci minha senha:** usuário aciona fluxo de recuperação (RF22).

**Pós-condições:** Sessão autenticada iniciada, com acesso restrito conforme perfil.

---

## UC02 — Cadastrar Novo Usuário (Barbeiro/Recepção)

**Atores:** Proprietário.

**Pré-condições:** Proprietário autenticado no sistema.

**Fluxo Principal:**
1. Proprietário acessa gestão de usuários.
2. Informa dados do novo usuário.
3. Define perfil de acesso (Barbeiro ou Recepção).
4. Sistema cria a conta.

**Pós-condições:** Novo usuário habilitado a autenticar-se com as permissões do perfil definido.

---

## UC03 — Criar Agendamento

**Atores:** Recepção/Barbeiro (ou Cliente, caso confirmado no diagnóstico como agendamento remoto).

**Pré-condições:** Cliente e serviço previamente cadastrados; usuário autenticado (quando aplicável).

**Fluxo Principal:**
1. Ator seleciona cliente, serviço e barbeiro desejado.
2. Sistema calcula automaticamente o horário de término com base na duração do serviço (RF05).
3. Sistema verifica disponibilidade do barbeiro no intervalo solicitado (RF06).
4. Sistema grava o agendamento como operação atômica no banco de dados (RNF09).
5. Sistema confirma o agendamento ao ator.

**Fluxos Alternativos:**
- **FA1 — Conflito de horário:** se o horário já estiver ocupado (inclusive por concorrência simultânea, conforme RNF09), o sistema rejeita a gravação e aciona o RF07, sugerindo os próximos horários disponíveis para o mesmo barbeiro ou outro profissional apto.
- **FA2 — Horário fora do expediente do barbeiro:** sistema impede a confirmação e informa o expediente vigente (RF06).

**Pós-condições:** Agendamento criado com status "Agendado" (RF10), horário bloqueado na agenda do barbeiro.

---

## UC04 — Reagendar Atendimento

**Atores:** Recepção/Barbeiro.

**Pré-condições:** Agendamento existente com status "Agendado".

**Fluxo Principal:**
1. Ator seleciona o agendamento.
2. Informa nova data/horário e/ou profissional.
3. Sistema repete a validação de disponibilidade (mesma lógica do UC03).
4. Confirma a alteração.

**Fluxos Alternativos:**
- **FA1 — Novo horário indisponível:** sistema rejeita e sugere alternativas (RF07).

**Pós-condições:** Agendamento atualizado; horário anterior liberado na agenda.

---

## UC05 — Cancelar Atendimento

**Atores:** Recepção/Barbeiro.

**Fluxo Principal:**
1. Ator seleciona o agendamento.
2. Confirma cancelamento.
3. Sistema altera o status para "Não Compareceu" ou remove o registro, conforme o motivo informado.
4. Horário é liberado imediatamente na agenda (RF09).

**Pós-condições:** Horário disponível novamente para novos agendamentos; indicador de cancelamento contabilizado no RF19 (taxa de cancelamento/não comparecimento).

---

## UC06 — Concluir Atendimento e Registrar Pagamento

**Atores:** Barbeiro/Recepção.

**Pré-condições:** Agendamento com status "Em Andamento".

**Fluxo Principal:**
1. Ator marca o atendimento como "Concluído" (RF10).
2. Sistema aciona a baixa automática dos insumos utilizados no estoque (RF13).
3. Ator registra a forma de pagamento e o valor recebido (RF15).
4. Sistema calcula a comissão devida ao barbeiro com base no percentual cadastrado (RF16).

**Fluxos Alternativos:**
- **FA1 — Estoque insuficiente do insumo:** sistema alerta o usuário no momento da baixa, sem impedir a conclusão do atendimento.

**Pós-condições:** Atendimento concluído, estoque atualizado, pagamento e comissão registrados, dados disponíveis para os relatórios (RF17, RF18, RF19).

---

## UC07 — Gerenciar Estoque e Alertas de Reposição

**Atores:** Proprietário/Recepção.

**Fluxo Principal:**
1. Sistema monitora continuamente a quantidade de cada produto (RF11).
2. Ao atingir o limite mínimo cadastrado, gera notificação (RF14).
3. Usuário providencia reposição e atualiza a quantidade em estoque manualmente.

**Pós-condições:** Estoque mantido acima do limite crítico, reduzindo risco de ruptura durante atendimentos.

---

## UC08 — Gerar Relatórios Financeiros e Estatísticos

**Atores:** Proprietário.

**Pré-condições:** Usuário autenticado com perfil autorizado (RF24/RNF06).

**Fluxo Principal:**
1. Proprietário seleciona período e filtro desejado.
2. Sistema agrega os dados de atendimentos concluídos e pagamentos registrados.
3. Exibe faturamento total, comissões devidas (RF17), ranking de serviços (RF18) e métricas do painel (RF19).

**Pós-condições:** Relatório exibido/exportável, sem exposição a usuários de outros perfis.

---

## UC09 — Executar Otimização de Alocação de Horários

**Atores:** Sistema (processo automático, acionado ao gerar sugestões de encaixe).

**Pré-condições:** Conjunto de agendamentos pendentes e barbeiros disponíveis no período.

**Fluxo Principal:**
1. Sistema avalia as combinações possíveis de barbeiro/horário/serviço em paralelo (RNF01).
2. Seleciona a alocação que minimiza tempo ocioso.
3. Registra o tempo de execução para fins de comparação sequencial vs. paralelo (RNF02).
4. Apresenta a sugestão de encaixe ao ator do UC03/UC04.

**Pós-condições:** Sugestão de horário disponibilizada com métrica de desempenho registrada para documentação técnica.