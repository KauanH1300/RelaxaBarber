# Testes da API com Postman

A [coleção RelaxaBarber | DevOps](../devops/postman/relaxabarber.postman_collection.json) usa o formato Postman v2.1. Cada requisição inclui exemplos de resposta e testes de status e conteúdo. O logout valida o status 204 e a ausência de corpo.

## Preparar e executar no Postman

1. Suba o [Compose acadêmico](devops-compose.md) com o esquema inicializado e o ADMIN fictício cadastrado.
2. Importe a coleção e o [ambiente local](../devops/postman/local.postman_environment.json). Selecione o ambiente e preencha apenas os valores locais de `equipe_email` e `equipe_senha`. Use a conta fictícia criada no preparo (por exemplo, `admin@relaxabarber.example`).
3. Deixe `filial_id` vazio quando a conta tiver acesso a uma única filial ativa. Para contas com várias filiais, informe o UUID da filial de demonstração.
4. Execute a **coleção inteira** com o Runner para que o login e o logout façam parte da mesma execução. Por padrão, a coleção verifica saúde, autenticação e leitura. Para exercitar o cadastro, defina `executar_escrita` como `true` no ambiente local.
5. Confira o relatório de testes e encerre a sessão com `POST /auth/logout` se tiver executado as requisições individualmente. Mantenha a senha e o token fora dos valores compartilhados, dos exemplos salvos e dos arquivos versionados.

| Fluxo | Cobertura |
|---|---|
| Disponibilidade | `GET /health` e `GET /ready` esperam 200. O exemplo 503 de prontidão documenta banco indisponível sem provocá-lo. |
| Autenticação | `GET /clientes` anônimo espera 401. `POST /auth/login` obtém o Bearer token, `GET /auth/me` valida a conta e `POST /auth/logout` encerra a sessão. |
| Consulta | `GET /clientes` autenticado verifica a lista e os campos de cada registro. |
| Cadastro local opcional | `POST /clientes` retorna 201. A repetição com a mesma chave precisa devolver o mesmo ID. As consultas por chave e por ID confirmam o registro e seus campos. |

O cadastro é permitido apenas com `base_url=http://localhost:18082` e opt-in explícito. Ele deixa um registro fictício no banco acadêmico. A coleção não contém operação de exclusão. Se houver perda de resposta, mantenha a chave, o telefone, a conta e a filial originais e consulte pela mesma chave antes de iniciar outro cadastro. Para gerar um cadastro independente, limpe `cadastro_chave`, `cadastro_telefone` e `cliente_id` no ambiente local antes de executar.

O [ambiente de nuvem](../devops/postman/nuvem.postman_environment.json) usa um domínio ilustrativo. Quando houver uma implantação de demonstração, configure sua URL HTTPS e use apenas uma conta fictícia dessa implantação. Nesse ambiente a pasta de cadastro é pulada.

## Executar com Newman

Copie o ambiente de exemplo para `.local-qa/postman.local.json` e preencha a cópia ignorada pelo Git com os dados fictícios. Se quiser validar o cadastro local, ative `executar_escrita` nessa cópia.

```console
npx --yes newman@6.2.1 run devops/postman/relaxabarber.postman_collection.json -e .local-qa/postman.local.json --ignore-redirects
```

O Newman retorna código diferente de zero quando uma asserção falha. O primeiro uso pode precisar baixar o Newman. Evite exportar ambientes preenchidos ou publicar relatórios que capturem corpos de autenticação.
