# Arquitetura do Sistema — RelaxaBarber

---

## 1. Visão Geral e Estilo Arquitetural

O **RelaxaBarber** adota o estilo arquitetural **Cliente-Servidor Desacoplado** estruturado em três camadas lógicas independentes (Apresentação, Aplicação e Persistência), com integração via API RESTful sob protocolo HTTPS.

A separação estrita de responsabilidades visa:

1. **Autonomia de Evolução:** Manutenção e escalabilidade independentes para cada camada sem impacto acoplado.
2. **Reuso de Regras de Negócio:** A mesma API atende à interface local do balcão (recepção/gerência) e ao autoatendimento remoto dos clientes.
3. **Restrição de Custo Operacional:** Arquitetura compatível com camadas gratuitas (*free tier*) de provedores modernos de hospedagem.

---

## 2. Diagrama Arquitetural da Solução

```
+-------------------------------------------------------------------------+
|                       CAMADA DE APRESENTAÇÃO                            |
|                  React.js (Vite + TypeScript)                           |
|                      Hospedagem: Vercel                                 |
+-------------------------------------------------------------------------+
                                  |
                                  | HTTPS / REST + Bearer JWT
                                  v
+-------------------------------------------------------------------------+
|                        CAMADA DE APLICAÇÃO                              |
|                      Python 3.12+ / FastAPI                             |
|                       Hospedagem: Render                                |
|                                                                          |
|  +-------------------+  +--------------------+  +--------------------+  |
|  |  API / Endpoints  |  | Schemas (Pydantic) |  |   RBAC Security    |  |
|  +-------------------+  +--------------------+  +--------------------+  |
|            |                                              |             |
|            +----------------------+-----------------------+             |
|                                   v                                     |
|                      +--------------------------+                       |
|                      |   Services (Business)    |                       |
|                      +--------------------------+                       |
|                               |             |                           |
|      +------------------------+             +-------------------+       |
|      | Chamada Interna (IPC)                                    |       |
|      v                                                          v       |
|  +--------------------------------+              +-------------------+  |
|  | Otimizador de Grade (RNF01)    |              |  SQLAlchemy 2.0   |  |
|  | (multiprocessing / ProcessPool)|              |     (ORM DDL)     |  |
|  +--------------------------------+              +-------------------+  |
+-------------------------------------------------------------|-----------+
                                                                |
                                                                | TCP (Pooling)
                                                                v
+-------------------------------------------------------------------------+
|                       CAMADA DE PERSISTÊNCIA                            |
|                   PostgreSQL Relacional (ACID)                          |
|                       Hospedagem: Supabase                              |
+-------------------------------------------------------------------------+
```

### Fluxo Operacional

1. O cliente HTTP (Web SPA) despacha requisições serializadas em JSON via HTTPS com token JWT.
2. A camada de aplicação valida o cabeçalho de autenticação e as permissões de acesso do perfil solicitante (RBAC).
3. Schemas do Pydantic realizam a validação estrutural e tipagem de entrada de dados.
4. A camada de serviços executa regras transacionais, aplicando locks no banco de dados para operações críticas de agendamento.
5. Caso seja solicitado agendamento com o parâmetro *"Sem preferência"*, o serviço invoca o motor de otimização em processos isolados via `multiprocessing`.
6. Transações aprovadas são persistidas atomicamente no PostgreSQL.

---

## 3. Componentes da Solução e Tecnologias

### 3.1. Camada de Apresentação (Frontend)
- **Tecnologias:** React.js, Vite, TypeScript, Axios.
- **Hospedagem:** Vercel.
- **Responsabilidade:** Renderização da interface de usuário em Single Page Application (SPA), consumo de endpoints autenticados, validações reativas de formulários e gerenciamento de estado local.

### 3.2. Camada de Aplicação (Backend)
- **Tecnologias:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic.
- **Hospedagem:** Render.
- **Responsabilidade:** Roteamento de requisições, validação tipada de dados, orquestração de regras de negócio, controle de sessão/JWT e orquestração do processamento concorrente.

### 3.3. Camada de Persistência (Banco de Dados)
- **Tecnologia:** PostgreSQL 15+.
- **Provedor:** Supabase Database Engine.
- **Responsabilidade:** Armazenamento relacional com garantia de conformidade ACID, execução de *triggers* de consistência, resolução de concorrência com locks a nível de linha (`FOR UPDATE`) e índices de busca operacional.

---

## 4. Arquitetura Interna do Backend (Layered Architecture)

O backend segue uma arquitetura em camadas bem delimitadas para atender ao requisito de manutenibilidade (RNF12):

```text
app/
├── api/
│   ├── dependencies.py       # Extração de contexto, injeção de dependência e checagem de RBAC
│   └── v1/
│       ├── endpoints/        # Controladores REST divididos por domínio (agendamentos, comandas, etc.)
│       └── router.py         # Registro e roteamento de rotas v1
├── core/
│   ├── config.py             # Leitura e parsing de variáveis de ambiente via Pydantic Settings
│   └── security.py           # Funções de hashing de senha e validação de tokens JWT
├── db/
│   ├── session.py            # Instanciação do engine SQLAlchemy e SessionLocal
│   └── base.py               # Importação de todos os modelos declarativos para o Alembic
├── models/                   # Mapeamento Objeto-Relacional (Entidades de banco)
├── schemas/                  # Contratos de dados de entrada/saída (DTOs serializáveis do Pydantic)
└── services/                 # Casos de uso e regras de negócio transacionais puras
    ├── agendamento_service.py
    ├── comanda_service.py
    └── otimizador/           # Algoritmos puros de grade desacoplados de conexões externas
```

### Papéis das Subcamadas

- **Endpoints (`api/`):** Capturam os parâmetros HTTP, injetam dependências (sessão de banco e usuário autenticado) e delegam a execução aos serviços.
- **Schemas (`schemas/`):** Asseguram tipagem estrita na entrada e saída, impedindo injeção de dados malformados na aplicação.
- **Services (`services/`):** Centralizam a lógica de negócio (cálculos financeiros, regras de antecedência e validações de conflito). Nenhuma regra de negócio deve residir diretamente no controlador REST.
- **Models (`models/`):** Definem a estrutura das tabelas, tipos de dados, chaves primárias/estrangeiras e constraints relacionais.

---

## 5. Arquitetura de Dados e Regras Transacionais

### 5.1. Segregação de Estoque e Saídas

Para eliminar ambiguidade financeira no uso de itens internos, o sistema adota estruturas relacionais separadas:

```
                  +-----------------------------------+
                  |              PRODUTO               |
                  | tipo: ENUM('INSUMO', 'REVENDA')    |
                  +-----------------------------------+
                       |                         |
        (Uso de bancada)                         (Venda balcão)
                       v                         v
        +-----------------------+       +-----------------------+
        |     ConsumoInsumo     |       |      ItemComanda      |
        | - agendamento_id (FK) |       | - comanda_id (FK)     |
        | - produto_id (FK)     |       | - produto_id (FK)     |
        | - quantidade (INT)    |       | - quantidade (INT)    |
        +-----------------------+       | - preco_unitario (NUM)|
                                         +-----------------------+
```

- **ConsumoInsumo:** Entidade operacional vinculada exclusivamente a um Agendamento. Realiza o débito do estoque físico de itens classificados como `INSUMO` no momento em que o atendimento atinge o status `CONCLUIDO`. Não gera cobrança financeira.
- **ItemComanda:** Entidade financeira vinculada exclusivamente a uma Comanda. Registra a venda comercial de itens do tipo `REVENDA` com registro histórico do preço unitário cobrado. Gera débito no estoque e soma valor ao faturamento da comanda.

### 5.2. O Modelo Financeiro de Comandas

O faturamento opera desacoplado da agenda:

- A **Comanda** atua como cabeçalho financeiro, podendo estar associada a um Agendamento ou diretamente a um Cliente (para vendas diretas de balcão).
- Os registros da entidade **Pagamento** quitam a Comanda (e nunca o agendamento de forma direta).
- Uma vez quitada integralmente (`total_pago == total_liquido`), o status da comanda passa para `FECHADA` e o cálculo de comissões devidas aos profissionais é apurado.

---

## 6. Controle de Concorrência e Integridade (RNF09)

Para mitigar condições de corrida (quando múltiplos clientes tentam alocar simultaneamente o mesmo profissional no mesmo intervalo), a aplicação não confia apenas em verificações em memória.

### Mecanismo de Bloqueio Pessimista

Ao submeter uma criação de agendamento, o backend executa:

```sql
SELECT id FROM agendamentos
WHERE barbeiro_id = :barbeiro_id
  AND status IN ('AGENDADO', 'EM_ANDAMENTO')
  AND (data_hora_inicio < :novo_fim AND data_hora_fim > :novo_inicio)
FOR UPDATE;
```

A cláusula `FOR UPDATE` bloqueia as linhas concorrentes dentro da transação atômica do PostgreSQL. Caso a query retorne registros, a transação sofre rollback imediato e a API retorna `HTTP 409 Conflict`, eliminando colisões de horário.

---

## 7. Controle de Acesso Baseado em Papéis (RBAC)

O controle de autorização é validado em cada requisição por meio de `dependencies` do FastAPI:

| Perfil | Acessos e Operações Permitidas | Restrições Estritas |
|---|---|---|
| **ADMIN** | Acesso irrestrito a configurações globais, comissões, relatórios e gestão de usuários. | Nenhuma restrição operacional. |
| **RECEPCAO** | Gestão da grade de agendamentos, cadastro de clientes, abertura de comandas e baixa de pagamentos. | Bloqueio total a relatórios consolidados de faturamento e taxas de comissão dos profissionais. |
| **BARBEIRO** | Consulta restrita à sua própria grade de horários, registro de baixa de insumos de bancada e consulta de comissões pessoais. | Proibido de operar o caixa (comandas/pagamentos) e de acessar agendas de terceiros. |
| **CLIENTE** | Solicitação e cancelamento de seus próprios agendamentos via autoatendimento e consulta ao catálogo digital da vitrine. | Proibido de sobrescrever tempos de serviço ou acessar qualquer módulo interno. |

---

## 8. Componente Computacional Avançado (RNF01 e RNF02)

### 8.1. Arquitetura do Mecanismo de Paralelização

Para a alocação de clientes com a opção "Sem preferência de profissional", o sistema executa uma avaliação combinatória dos horários vagos de todos os barbeiros aptos. Devido ao Global Interpreter Lock (GIL) do Python, operações com carga computacional intensiva de CPU não escalam de forma transparente com threads convencionais.

A solução utiliza o módulo `multiprocessing.ProcessPoolExecutor`:

```
                       Backend (FastAPI Main Loop)
                                 |
              +------------------+------------------+
              |           Dispatch Payload           |
              v                                     v
       [Worker Process 1]                    [Worker Process N]
       (Core CPU Dedicado)                   (Core CPU Dedicado)
              |                                     |
    Avalia Janelas Barbeiro A             Avalia Janelas Barbeiro B
              \                                     /
               +-----------------+-----------------+
                                 |
                     Consolidação IPC (Pipes)
                                 v
                 Ordenação por Ociosidade Mínima
                                 v
                       Retorno da Resposta
```

### 8.2. Métrica de Auditoria e Speedup (RNF02)

Para validação acadêmica e técnica, a rota `/agendamentos/sugestoes-encaixe` calcula e expõe a métrica de eficiência computacional:

$$
\text{Speedup} = \frac{T_{\text{sequencial}}}{T_{\text{paralelo}}}
$$

Os tempos $T_{\text{sequencial}}$ e $T_{\text{paralelo}}$ são mensurados via timers de alta resolução (`time.perf_counter`) e incluídos no objeto de metadados da resposta HTTP.

---

## 9. Matriz de Infraestrutura, Comunicação e Custos (RNF11)

| Camada | Tecnologia | Protocolo de Comunicação | Hospedagem | Modelo de Custo |
|---|---|---|---|---|
| Apresentação | React.js (SPA) | HTTPS | Vercel | Gratuito (*Free tier*) |
| Aplicação | Python / FastAPI | HTTPS (Origem) / TCP (Destino) | Render | Gratuito (*Free tier*) |
| Persistência | PostgreSQL 15+ | TCP / Pooling (porta 5432 / 6543) | Supabase | Gratuito (*Free tier*) |
| Otimizador | Python `multiprocessing` | IPC (Comunicação Interprocessos nativa) | Local ao Host Render | Custo zero (CPU do host) |
| Autenticação | OAuth2 Bearer / JWT | HTTPS Header (`Authorization`) | Supabase / Render | Gratuito (*Free tier*) |

A disponibilidade contínua dos serviços hospedados em camadas gratuitas é preservada por meio de rotinas automatizadas de *keep-alive* configuradas via GitHub Actions.
