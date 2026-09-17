# 💈 RelaxaBarber — Sistema de Gestão para Barbearias

> Sistema web full-stack para digitalização operacional, controle financeiro, gestão de estoque e agendamento inteligente com otimização paralela de horários para barbearias físicas.

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)

---

## 📌 Sumário
- [Sobre o Projeto](#-sobre-o-projeto)
- [Arquitetura da Solução](#-arquitetura-da-solução)
- [Regras de Negócio Inegociáveis](#-regras-de-negócio-inegociáveis)
- [Motor de Otimização Concorrente](#-motor-de-otimização-concorrente)
- [Controle de Acesso Baseado em Papéis (RBAC)](#-controle-de-acesso-baseado-em-papéis-rbac)
- [Estrutura do Repositório](#-estrutura-do-repositório)
- [Variáveis de Ambiente](#-variáveis-de-ambiente)
- [Como Executar Localmente](#-como-executar-localmente)
  - [Pré-requisitos](#pré-requisitos)
  - [Backend (FastAPI)](#backend-fastapi)
  - [Frontend (React + Vite)](#frontend-react--vite)
- [Requisitos do Sistema](#-requisitos-do-sistema)
- [Equipe de Desenvolvimento](#-equipe-de-desenvolvimento)

---

## 📖 Sobre o Projeto

O **RelaxaBarber** foi concebido para erradicar o controle informal e mitigar gargalos operacionais em micro e pequenas barbearias de bairro. O sistema resolve as dores clássicas de concorrência de agenda, ausência de controle financeiro automatizado e inconsistências no estoque físico causadas pela falta de distinção entre insumos de bancada e produtos de revenda comercial.

---

## 🏗 Arquitetura da Solução

A aplicação é estruturada em **3 camadas desacopladas**, operando exclusivamente com soluções internas, sem dependência de serviços proprietários ou bibliotecas externas de IA:

1. **Camada de Apresentação (Frontend):** SPA em React.js inicializada via Vite, interface responsiva adaptada a desktop e mobile, consumindo a API via HTTPS com autenticação JWT.
2. **Camada de Aplicação (Backend):** Python 3.11+ utilizando FastAPI, validação estrita com Pydantic v2 e persistência mapeada via SQLAlchemy ORM.
3. **Camada de Persistência (Banco de Dados):** PostgreSQL com restrições relacionais estritas, índices compostos e transações ACID para prevenir condições de corrida em agendamentos concorrentes.

```text
[ React SPA (Vite) ]  <--- HTTPS / REST (JSON + JWT) --->  [ FastAPI Application ]
                                                                   │
                                           ┌───────────────────────┴───────────────────────┐
                                           ▼                                               ▼
                           [ PostgreSQL Relational DB ]                  [ ProcessPoolExecutor (IPC) ]
                             (Transações ACID & Constraints)               (Motor Heurístico de Grade)
```

---

## ⚖ Regras de Negócio Inegociáveis

### 1. Separação Estrita de Estoque e Saídas
* **`ConsumoInsumo` (Bancada):** Materiais descartáveis de uso interno operacional (lâminas, golas descartáveis, toalhas, loções pós-barba). Cada registro é atrelado diretamente a um `Agendamento` com quantidade consumida. **Ação:** Decrementa o saldo do estoque físico sem gerar qualquer cobrança ou reflexo financeiro ao cliente.
* **`ItemComanda` (Comercial/Faturado):** Produtos de revenda de balcão (pomadas, tônicos, bebidas). Cada registro é associado a uma `Comanda`, contendo preço unitário registrado no ato e quantidade. **Ação:** Cobra o cliente e apura comissão do atendente/barbeiro quando configurado.

### 2. Fluxo Financeiro Baseado em Comandas
* A entidade **`Comanda`** é o cabeçalho financeiro mandatório da operação.
* Uma `Comanda` pode originar-se de um `Agendamento` (atendimento finalizado) ou diretamente de um `Cliente` (venda balcão sem serviço agendado).
* O **`Pagamento`** (Dinheiro, Pix, Cartão) quita a **`Comanda`** e não o agendamento de forma isolada.

### 3. Modelagem de Usuários e Extensões 1:1
* Tabela base `USUARIO` armazena credenciais unificadas (`id`, `nome`, `email`, `senha_hash`, `role`).
* Especializações via relacionamentos 1:1 exclusivos:
  * `CLIENTE`: Dados de preferências de corte, histórico clínico/técnico e restrições.
  * `BARBEIRO`: Jornada de trabalho, intervalos, taxa padrão e comissões customizadas por serviço.

### 4. Parametrizador Central (`ConfiguracaoBarbearia`)
* Todas as regras globais de negócio são lidas da tabela de parâmetros:
  * Horários de funcionamento por dia da semana.
  * Tempo de antecedência mínima para reserva de horários.
  * Tempo de antecedência mínima para cancelamento ou reagendamento.

---

## ⚡ Motor de Otimização Concorrente

Quando o cliente opta por realizar o agendamento através da opção **"Sem preferência de profissional"**, o sistema executa um algoritmo combinatório para encontrar a alocação que minimize janelas de ociosidade na grade dos barbeiros:

* **Execução Não-Bloqueante:** Utiliza `concurrent.futures.ProcessPoolExecutor` via IPC (Inter-Process Communication), isolando o custo de processamento de CPU do loop assíncrono do FastAPI (`uvicorn`).
* **Auditoria de Desempenho (*Speedup*):** Registra os tempos de execução nos modos sequencial e paralelo, expondo métricas técnicas para monitoramento de ganho computacional.

---

## 🔐 Controle de Acesso Baseado em Papéis (RBAC)

| Papel (Role) | Agenda | Atendimentos e Insumos | Comandas e Caixa | Gestão e Relatórios |
| :--- | :--- | :--- | :--- | :--- |
| **Admin / Dono** | Total | Acesso total | Acesso total | Cadastros, DRE, parametrização, comissões |
| **Recepção** | Total | Encaixes imediatos | Abertura, fechamento e cobrança | Cadastro de clientes e agendamentos |
| **Barbeiro** | Individual | Baixa de insumos de bancada | Proibido operar caixa | Apenas histórico próprio e comissão |
| **Cliente** | Individual | Autoagendamento / Histórico | Apenas visualização da própria fatura | Vitrine digital de produtos |

---

## 📂 Estrutura do Repositório

```text
RelaxaBarber/
├──.github/
|   ├── workflows/
├──backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── endpoints/    # Rotas separadas por domínio (auth, agenda, comanda)
│   │   │   │   └── router.py     # Agrupador central de rotas
│   │   │   └── deps.py           # Injeção de dependências (get_db, auth)
│   │   ├── core/
│   │   │   ├── config.py         # Carregamento de env vars (Pydantic BaseSettings)
│   │   │   └── security.py       # Hashing de senhas e geração de JWT
│   │   ├── db/
│   │   │   ├── base.py           # Base declarativa SQLAlchemy
│   │   │   └── session.py        # Engine e fábrica de sessões (sessionmaker)
│   │   ├── models/               # Entidades SQLAlchemy (Usuario, Agendamento, Comanda, etc.)
│   │   ├── schemas/              # Schemas Pydantic para validação de DTOs
│   │   ├── services/             # Regras de negócio, serviços de estoque e financeiro
│   │   ├── optimization/         # Algoritmo heurístico paralelo (ProcessPoolExecutor)
│   │   └── main.py               # Instanciação da aplicação FastAPI
│   ├── alembic/                  # Versionamento de migrações de banco
│   ├── requirements.txt          # Dependências do ecossistema Python
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── assets/               # Imagens e ícones estáticos
│   │   ├── components/           # Componentes atômicos e estruturais
│   │   ├── context/              # Contextos React (AuthContext, ThemeContext)
│   │   ├── pages/                # Views (Dashboard, Grade, Comandas, Estoque, Vitrine)
│   │   ├── routes/               # Configuração do React Router com guardas de perfil
│   │   ├── services/             # Clientes HTTP (Axios) integrados com a API REST
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── .env.example
└── README.md
```

---

## 🔑 Variáveis de Ambiente

Antes de iniciar os serviços, crie os arquivos de variáveis baseando-se nos exemplos:

### Backend (`backend/.env`)
```ini
# Configuração Geral
PROJECT_NAME="RelaxaBarber API"
ENV="development"
DEBUG=True

# Conexão com o PostgreSQL
DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/relaxabarber"

# Criptografia e Autenticação
SECRET_KEY="SUA_CHAVE_SECRETA_JWT_AQUI_DEVE_SER_LONGA_E_SEGURA"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=480

# CORS
BACKEND_CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173"]
```

### Frontend (`frontend/.env`)
```ini
VITE_API_BASE_URL="http://localhost:8000/api/v1"
```

---

## 🚀 Como Executar Localmente

### Pré-requisitos
* **Python:** Versão 3.11 ou superior
* **Node.js:** Versão 18 ou superior
* **PostgreSQL:** Instância ativa com base de dados criada (`relaxabarber`)

---

### Backend (FastAPI)

1. Entre no diretório do backend:
   ```bash
   cd backend
   ```

2. Crie e ative o ambiente virtual:
   ```bash
   python -m venv venv
   # No Linux/macOS:
   source venv/bin/activate
   # No Windows:
   venv\Scripts\activate
   ```

3. Instale as dependências:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Aplique as migrações do banco de dados:
   ```bash
   alembic upgrade head
   ```

5. Inicialize a API via Uvicorn:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   * A documentação interativa Swagger UI estará disponível em: `http://localhost:8000/docs`
   * A documentação alternativa Redoc estará disponível em: `http://localhost:8000/redoc`

---

### Frontend (React + Vite)

1. Entre no diretório do frontend:
   ```bash
   cd frontend
   ```

2. Instale as dependências:
   ```bash
   npm install
   ```

3. Inicie o servidor de desenvolvimento:
   ```bash
   npm run dev
   ```
   * A interface web estará acessível em: `http://localhost:5173`

---

## 📋 Requisitos do Sistema

* **Requisitos Funcionais Principais:** Gestão de jornada dos profissionais, autoagendamento pelo cliente, validação atômica de horários livres, baixa automática de insumos de bancada sem custo adicional, fechamento de comandas de clientes e vendas de balcão avulsas, painel analítico com cálculo automático de repasses e comissões.
* **Requisitos Não Funcionais Críticos:** Comunicação restrita a HTTPS, senhas hasheadas utilizando algoritmos robustos, tempo de resposta inferior a 2 segundos para operações de leitura/escrita convencionais e garantia de não-bloqueio através de processos isolados no cálculo combinatorial da grade.

---

## 👥 Equipe de Desenvolvimento

Projeto concebido e desenvolvido no âmbito acadêmico

* **Álvaro Amaral Oliveira** 
* **Ian Luka Ferreira Rosa** 
* **Kauan Henrique Barbosa da Costa** 
* **Kleiner Maurício Silva de Sá** 
* **Murilo William Trindade Guedes** 