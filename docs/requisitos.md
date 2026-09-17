# Especificação de Requisitos — RelaxaBarber

---

# 1. Requisitos Funcionais (RF)

## 1.1. Gestão de Cadastros e Pessoas

*   **RF01 — Cadastro e Jornada dos Barbeiros:** O sistema deve permitir cadastrar, visualizar, editar e inativar profissionais da barbearia, definindo jornada de trabalho individualizada (horários de início, término e intervalo de almoço por dia da semana).
*   **RF02 — Cadastro e Perfil do Cliente:** O sistema deve permitir o cadastro de clientes contendo: nome completo, telefone, e-mail (utilizado para autenticação/login), data de nascimento e campo de texto livre para observações e preferências técnicas (ex.: alergias a produtos, estilos de corte preferidos).
*   **RF03 — Histórico de Atendimentos do Cliente:** O sistema deve disponibilizar uma linha do tempo individual por cliente com todos os atendimentos realizados, contendo datas, barbeiros responsáveis, serviços executados, produtos consumidos ou adquiridos, valores pagos e observações[cite: 1].
*   **RF04 — Cadastro de Serviços:** O sistema deve permitir cadastrar, editar e inativar serviços oferecidos (ex.: corte simples, barba, química), informando nome, preço e tempo estimado de duração[cite: 1].
*   **RF05 — Parametrização de Comissões por Barbeiro e Serviço:** O sistema deve permitir ao Administrador/Proprietário personalizar percentuais de comissão específicos por combinação de barbeiro e serviço (ex.: Barbeiro A recebe 45% em corte simples, mas 30% em processos químicos), mantendo um percentual padrão caso não haja personalização[cite: 1].

---

## 1.2. Agendamento e Horários

*   **RF06 — Criação de Agendamento:** O sistema deve permitir agendar atendimentos associando cliente, barbeiro, serviço, data e horário de início, calculando o horário de término automaticamente com base na duração do serviço[cite: 1].
*   **RF07 — Ajuste Manual de Duração do Atendimento (Sobrescrita):** O sistema deve permitir que usuários internos autorizados (Barbeiro e Recepção) editem manualmente o tempo estimado de duração ou o horário de término de um atendimento na criação ou edição da reserva, recalculando o intervalo bloqueado na grade[cite: 1]. Essa edição deve ser bloqueada para o perfil Cliente[cite: 1].
*   **RF08 — Agendamento de Autoatendimento pelo Cliente:** O sistema deve disponibilizar interface responsiva para que o próprio cliente autenticado solicite seu agendamento, permitindo optar por um barbeiro específico ou selecionar a opção "Sem preferência"[cite: 1].
*   **RF09 — Atendimento Imediato sem Agendamento Prévio (Encaixe):** O sistema deve permitir à recepção registrar o início de um atendimento presencial avulso diretamente na grade, alocando um barbeiro livre no momento ou aproveitando o cancelamento/não comparecimento de um horário vago[cite: 1].
*   **RF10 — Validação de Disponibilidade e Parâmetros de Antecedência:** O sistema deve validar conflitos de horários e impedir marcações simultâneas para o mesmo profissional ou fora de sua jornada de trabalho[cite: 1]. Deve também aplicar regras parametrizáveis pela barbearia de tempo mínimo de antecedência para criação e cancelamento de horários[cite: 1].
*   **RF11 — Sugestão de Encaixe de Horários:** O sistema deve sugerir intervalos disponíveis que priorizem o preenchimento contínuo da grade (minimizando tempos vagos entre cortes) e distribuir os agendamentos quando o cliente não tiver preferência por um barbeiro específico[cite: 1].
*   **RF12 — Reagendamento e Cancelamento de Atendimentos:** O sistema deve permitir remarcar ou cancelar atendimentos, liberando imediatamente o horário na agenda do profissional e mantendo o histórico da ação[cite: 1].
*   **RF13 — Atualização de Status do Atendimento:** O sistema deve permitir alterar o estado do agendamento (Agendado, Em Andamento, Concluído ou Não Compareceu)[cite: 1].
*   **RF14 — Bloqueio de Horário:** O sistema deve permitir que o barbeiro ou proprietário bloqueie manualmente um intervalo específico na agenda, impedindo novos agendamentos naquele período, sem necessidade de cadastrar um atendimento fictício[cite: 1].

---

## 1.3. Estoque e Catálogo de Produtos (Vitrine)

*   **RF15 — Cadastro de Produtos:** O sistema deve permitir cadastrar e editar produtos, separando-os em Insumos de Consumo Interno (lâminas, toalhas descartáveis, cremes) e Itens de Revenda (pomadas, óleos, minoxidil), informando nome, preço de custo, preço de venda (quando aplicável), comissão do barbeiro pela venda (quando aplicável), estoque atual e estoque mínimo[cite: 1].
*   **RF16 — Vitrine Digital de Produtos (Catálogo de Consulta):** O sistema deve disponibilizar uma tela de catálogo visual aberta para os clientes consultarem os produtos disponíveis no estabelecimento, visualizando nome, descrição, foto e preço de venda balcão (sem checkout ou pagamento online pelo app)[cite: 1].
*   **RF17 — Baixa Automática de Insumos:** O sistema deve debitar do estoque os insumos consumidos assim que o atendimento for marcado como "Concluído"[cite: 1].
*   **RF18 — Notificação de Estoque Mínimo:** O sistema deve alertar o usuário quando a quantidade de um produto atingir ou ficar abaixo do limite mínimo cadastrado[cite: 1].

---

## 1.4. Módulo Financeiro e Estatísticas do Negócio

*   **RF19 — Registro de Pagamentos:** O sistema deve permitir registrar a forma de pagamento (Dinheiro, Pix, Cartão) e o valor recebido na conclusão do atendimento ou na venda presencial de produtos da vitrine[cite: 1].
*   **RF20 — Cálculo de Comissões:** O sistema deve apurar automaticamente o valor a ser repassado para cada barbeiro com base nos serviços concluídos no período e nos percentuais cadastrados[cite: 1].
*   **RF21 — Relatório de Faturamento:** O sistema deve gerar relatórios com o total faturado no dia, semana ou mês, detalhando valores brutos e comissões devidas[cite: 1].
*   **RF22 — Ranking de Serviços Mais Pedidos:** O sistema deve exibir relatórios e indicadores dos serviços mais consumidos no estabelecimento por período, identificando quais geram maior receita e volume[cite: 1].
*   **RF23 — Painel de Estatísticas Básicas (Dashboard):** O sistema deve apresentar métricas gerais da operação, tais como: total de clientes atendidos no mês, taxa de cancelamento/não comparecimento, ticket médio por atendimento e dias/horários de maior movimento na barbearia[cite: 1].

---

## 1.5. Segurança e Controle de Acesso

*   **RF24 — Autenticação de Usuários:** O sistema deve permitir que usuários cadastrados façam login por meio de e-mail/usuário e senha, exibindo mensagem de erro em caso de credenciais inválidas[cite: 1].
*   **RF25 — Cadastro de Acesso por Perfil:** O sistema deve permitir que o Proprietário cadastre novos usuários (barbeiros, recepção e clientes), definindo o perfil de acesso de cada um no momento da criação da conta[cite: 1].
*   **RF26 — Recuperação de Senha:** O sistema deve permitir que o usuário redefina sua senha em caso de esquecimento, mediante verificação por e-mail ou WhatsApp cadastrado[cite: 1].
*   **RF27 — Encerramento de Sessão (Logout):** O sistema deve permitir que o usuário encerre sua sessão ativa a qualquer momento, exigindo nova autenticação para acesso subsequente[cite: 1].
*   **RF28 — Controle de Permissões por Perfil:** O sistema deve restringir o acesso às funcionalidades conforme o perfil autenticado (Proprietário: acesso total, incluindo financeiro e comissões; Barbeiro: agenda e histórico próprios; Recepção: agendamento e cadastro de cliente, sem acesso a relatórios financeiros ou comissões)[cite: 1].

---

# 2. Requisitos Não Funcionais (RNF)

## 2.1. Performance e Otimização

*   **RNF01 — Processamento Paralelo do Algoritmo de Otimização:** O algoritmo de sugestão de encaixe de horários (RF07) deve avaliar as combinações candidatas de alocação (barbeiro × horário × serviço) de forma paralela, e não sequencial, utilizando múltiplos processos/threads[cite: 1].
*   **RNF02 — Métrica de Ganho de Desempenho:** O sistema deve registrar e disponibilizar o tempo de execução do algoritmo de otimização em modo sequencial e em modo paralelo, permitindo comparação objetiva do ganho de desempenho (speedup) obtido[cite: 1].
*   **RNF03 — Tempo de Resposta da Aplicação:** As operações de consulta e gravação mais frequentes (agendamento, consulta de disponibilidade, registro de atendimento) devem ser concluídas em até 2 segundos sob condições normais de uso[cite: 1].

---

## 2.2. Segurança

*   **RNF04 — Criptografia de Senhas:** As senhas dos usuários devem ser armazenadas de forma criptografada (hash), nunca em texto plano[cite: 1].
*   **RNF05 — Comunicação Segura:** A comunicação entre a interface e o backend deve ocorrer via HTTPS[cite: 1].
*   **RNF06 — Confidencialidade de Dados Financeiros:** Informações de faturamento e comissões devem ser acessíveis exclusivamente a usuários com perfil autorizado (Proprietário), conforme definido no RF24[cite: 1].

---

## 2.3. Usabilidade

*   **RNF07 — Interface de Baixa Curva de Aprendizado:** A interface deve ser simples e objetiva, com poucos passos por tela, adequada a usuários com baixa familiaridade com sistemas digitais — considerando o perfil real do proprietário e da equipe da barbearia atendida[cite: 1].
*   **RNF08 — Feedback Visual de Ações:** O sistema deve fornecer confirmação visual clara para toda ação crítica (agendamento criado, atendimento concluído, estoque atualizado), evitando ambiguidade sobre o resultado de uma operação[cite: 1].

---

## 2.4. Confiabilidade e Disponibilidade

*   **RNF09 — Consistência de Dados na Concorrência:** O sistema deve impedir que dois usuários agendem, simultaneamente, o mesmo horário para o mesmo barbeiro (condição de corrida), garantindo consistência mesmo sob acesso concorrente[cite: 1].
*   **RNF10 — Tratamento de Falhas:** Erros de conexão ou falhas de operação devem ser comunicados ao usuário de forma clara, sem perda dos dados já preenchidos no formulário em andamento[cite: 1].

---

## 2.5. Custo e Infraestrutura

*   **RNF11 — Custo Zero de Operação:** O sistema deve utilizar exclusivamente tecnologias open-source e infraestrutura de hospedagem gratuita (free tier), sem custo recorrente para o parceiro[cite: 1].

---

## 2.6. Manutenibilidade

*   **RNF12 — Arquitetura Modular:** O sistema deve seguir uma arquitetura em camadas com separação de responsabilidades (ex.: rotas, serviços, regras de negócio, acesso a dados), permitindo manutenção e evolução independente de cada módulo[cite: 1].
*   **RNF13 — Versionamento de Código:** Todo o código-fonte deve ser versionado em repositório Git público, com histórico de commits individualizado por integrante da equipe[cite: 1].