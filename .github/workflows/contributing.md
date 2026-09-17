# Guia de Contribuição e Fluxo Git / Pull Requests — RelaxaBarber

Este documento é o guia prático e obrigatório para todos os desenvolvedores do projeto **RelaxaBarber** (Repositório: [`KauanH1300/RelaxaBarber`](https://github.com/KauanH1300/RelaxaBarber)).

Siga este roteiro rigorosamente para manter a estabilidade da arquitetura, evitar conflitos de código e assegurar que as regras de negócio sejam respeitadas.

---

## 1. Estrutura de Branches

- **`main`**: Código de produção, estável e testado. **Commits diretos são bloqueados.**
- **`develop`**: Branch principal de integração. É a base de onde saem todas as branches de trabalho e o destino de todos os Pull Requests. **Commits diretos são bloqueados.**
- **Branches de Trabalho:** Devem ser criadas sempre a partir de `develop`, seguindo a convenção de nomenclatura:
  - `feat/<nome-da-feature>`: Novas funcionalidades (ex.: `feat/baixa-insumos-agendamento`)
  - `fix/<descricao-do-bug>`: Correções de bugs (ex.: `fix/conflito-horario-bloqueado`)
  - `refactor/<o-que-mudou>`: Melhorias de código sem alteração de funcionalidade (ex.: `refactor/service-comissoes`)
  - `docs/<conteudo>`: Alterações em documentação (ex.: `docs/atualizacao-contributing`)

---

## 2. Padrão de Commits (Conventional Commits)

Escreva mensagens de commit claras e semânticas em português:

- `feat:` Implementação de nova funcionalidade
- `fix:` Correção de bug
- `refactor:` Refatoração de código sem impacto visual ou de regra
- `test:` Adição ou modificação de testes automatizados
- `docs:` Alterações em arquivos de documentação
- `chore:` Atualização de dependências, configs de build ou tooling

**Exemplos válidos:**

```
feat: adiciona baixa automatica de insumos ao concluir agendamento
fix: impede pagamento parcial sem criacao de comanda ativa
test: adiciona testes unitarios para calculo de comissao
```

---

## 3. Passo a Passo do Fluxo de Trabalho (Guia de Comandos Git)

### Passo 1: Atualizar a branch local `develop`

Antes de criar uma nova branch, puxe as alterações mais recentes do repositório remoto:

```bash
# Vá para a branch develop
git checkout develop

# Baixe as alterações mais recentes da develop remota
git pull origin develop
```

### Passo 2: Criar e alternar para sua branch de funcionalidade

Crie sua branch a partir da develop já atualizada:

```bash
# Cria e entra na nova branch
git checkout -b feat/baixa-insumos-agendamento
```

Para verificar em qual branch você está:

```bash
git branch
```

### Passo 3: Alternar entre branches de trabalho

Se você precisar pausar sua tarefa para conferir outra branch:

```bash
# 1. Certifique-se de salvar ou commitar seus arquivos modificados
# 2. Para voltar para a develop:
git checkout develop

# 3. Para retornar para a sua branch:
git checkout feat/baixa-insumos-agendamento
```

### Passo 4: Desenvolver e realizar commits atômicos

Faça commits incrementais e objetivos:

```bash
# Verifique o estado dos arquivos modificados
git status

# Adicione arquivos específicos para staging (evite 'git add .')
git add src/services/estoque_service.py src/models/consumo_insumo.py

# Registre o commit
git commit -m "feat: adiciona validacao de estoque minimo na saida de insumo"
```

### Passo 5: Atualizar sua branch com a develop antes do envio (Prevenção de Conflitos)

Se a develop avançou enquanto você trabalhava, sincronize sua branch via rebase:

```bash
# 1. Baixe o estado atualizado do GitHub
git fetch origin

# 2. Aplique seus commits sobre a develop mais recente
git rebase origin/develop
```

**Se houver conflitos no rebase:**

1. Abra os arquivos apontados com conflito no seu editor e resolva as marcações (`<<<<<<<`, `=======`, `>>>>>>>`).
2. Adicione os arquivos resolvidos:

   ```bash
   git add <arquivo_resolvido>
   ```

3. Continue o rebase (não faça commit manual):

   ```bash
   git rebase --continue
   ```

   *(Se precisar cancelar o rebase e voltar ao estado anterior: `git rebase --abort`)*

### Passo 6: Executar a validação de qualidade local

Nenhum PR deve ser aberto sem passar nas validações locais.

**Backend (Python / FastAPI):**

```bash
# Formatação e checagem de estilo
ruff check .
black --check .

# Verificação de tipagem estrita
mypy src/

# Testes automatizados
pytest
```

**Frontend (React / Vite):**

```bash
# Linting e compilação de tipos TypeScript
npm run lint
npm run build
```

### Passo 7: Enviar a branch para o repositório remoto

Para o primeiro envio da branch:

```bash
git push -u origin feat/baixa-insumos-agendamento
```

Para envios posteriores na mesma branch:

```bash
git push
```

> **Atenção:** Caso tenha feito `git rebase`, pode ser necessário forçar o push com segurança:
>
> ```bash
> git push --force-with-lease
> ```

---

## 4. Como Abrir o Pull Request (PR) no GitHub

1. Acesse o repositório: [github.com/KauanH1300/RelaxaBarber](https://github.com/KauanH1300/RelaxaBarber).
2. O GitHub exibirá um aviso sugerindo **"Compare & pull request"**. Clique nele.
3. **Atenção crítica às branches:**
   - **Base branch (destino):** `develop` (nunca selecione `main`)
   - **Compare branch (origem):** `feat/sua-branch`
4. **Título do PR:** Utilize o mesmo padrão semântico do commit.
   - Exemplo: `feat(estoque): implementa baixa de ConsumoInsumo sem cobranca`
5. **Descrição do PR:** Preencha o template obrigatório:
   - Descreva detalhadamente o que foi implementado/corrigido.
   - Indique se houve alterações em modelos de banco (`models.py`) ou migrações Alembic.
   - Marque os itens do checklist (testes, tipagem, linters).
6. **Reviewers:** Atribua pelo menos 1 integrante do grupo no campo Reviewers.
7. Clique em **"Create pull request"**.

---

## 6. Code Review e Ajustes

- O PR necessita da aprovação de pelo menos um colega para merge.
- Caso o revisor solicite alterações (**Changes requested**):
  1. Não feche nem abra outro PR.
  2. Faça as correções na mesma branch local.
  3. Execute os testes locais novamente.
  4. Faça o commit e execute `git push`. O Pull Request será atualizado automaticamente.
- Após todas as aprovações e checks automatizados verdes, o merge na branch `develop` será liberado.