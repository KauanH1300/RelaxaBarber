# Docker Compose da disciplina de DevOps

Para adicionar o Zabbix e o Grafana à demonstração, consulte o [guia de monitoramento acadêmico](devops-monitoramento.md).
Para verificar a API no Postman ou no Newman, use a [coleção de testes da disciplina](devops-postman.md).

O projeto `relaxabarber-academico` executa o React e o FastAPI na imagem de produção e o PostgreSQL 16 em um contêiner separado. O banco fica em uma rede interna, sem porta publicada, com volume nomeado exclusivo. A aplicação é publicada apenas no loopback, em [localhost:18082](http://localhost:18082).

## Preparar

É necessário Docker com Compose v2. O primeiro build precisa baixar imagens e dependências de Python e Node se elas não estiverem em cache. Em PowerShell, copie o exemplo, gere valores locais e mantenha o arquivo fora do Git.

```powershell
Copy-Item devops/.env.example devops/.env.academico
$valores = foreach ($nome in 'DEVOPS_DB_ADMIN_PASSWORD','DEVOPS_DB_APP_PASSWORD','DEVOPS_SECRET_KEY') {
    $hex = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant()
    "$nome=$hex"
}
$valores | Set-Content -Encoding ascii devops/.env.academico
```

O exemplo de geração usa PowerShell 7. No Windows PowerShell 5.1 ou em outro shell, preencha os três campos com valores aleatórios hexadecimais de 64 caracteres. Guarde o mesmo arquivo enquanto usar o volume, pois o PostgreSQL só configura os logins na primeira inicialização.

```console
docker compose --env-file devops/.env.academico -f compose.devops.yml config --quiet
docker compose --env-file devops/.env.academico -f compose.devops.yml run --rm --build esquema
docker compose --env-file devops/.env.academico -f compose.devops.yml run --rm esquema python /preparo/preparar.py admin
docker compose --env-file devops/.env.academico -f compose.devops.yml up -d --wait api
```

O serviço `esquema` aplica `alembic upgrade head` explicitamente, incluindo a extensão `btree_gist` e as políticas das migrações. Em seguida, concede os privilégios de runtime do esquema legado, usando a mesma lista da suíte PostgreSQL do repositório. O PostgreSQL provisiona os papéis na criação do volume. A API conecta com um login restrito, membro do papel `relaxabarber_runtime`, sem privilégios administrativos. O segundo comando de preparo cria opcionalmente um ADMIN fictício (`admin@relaxabarber.example`) vinculado à filial inicial e solicita a senha sem eco no terminal.

## Conferir a demonstração

- Abra [localhost:18082](http://localhost:18082), entre com o ADMIN local e cadastre um cliente fictício. Confirme a leitura na lista.
- [`/health`](http://localhost:18082/health) verifica o processo e é usado pelo Compose. [`/ready`](http://localhost:18082/ready) verifica a conexão ao banco com `SELECT 1`. O sucesso de `/ready` não certifica a revisão Alembic.
- Use `docker compose --env-file devops/.env.academico -f compose.devops.yml stats --no-stream` para medir a RAM durante a demonstração.
- Para parar e preservar o banco, use `docker compose --env-file devops/.env.academico -f compose.devops.yml down`.

Após um login e um cadastro de cliente no Docker Desktop, uma amostra registrou cerca de 76 MiB para a aplicação e 40 MiB para o PostgreSQL. Essa medição não inclui o Docker Desktop, o navegador ou o pico do build.

O fluxo de demonstração da equipe e o PostgreSQL funcionam localmente. As integrações de SMTP e Supabase Storage não são configuradas neste Compose. Envio de e-mails, recuperação/ativação por código entregue por e-mail e upload de fotos da vitrine ficam indisponíveis.
