# Monitoramento acadêmico

O arquivo `compose.monitoramento.yml` complementa o [Compose acadêmico](devops-compose.md). O Zabbix verifica `/health` e `/ready` da API a cada 15 segundos. O Grafana consulta o histórico do Zabbix por uma conta com leitura restrita ao grupo da aplicação.

O PostgreSQL do Zabbix e o Grafana têm volumes próprios. A rede das sondas liga o servidor Zabbix à API. O banco da aplicação permanece em sua rede interna original. As duas interfaces do monitoramento são publicadas somente no loopback. Os arquivos ficam fora do contexto de build do Dockerfile de produção pela lista de inclusão do `.dockerignore` da raiz.

## Iniciar

1. Prepare o esquema acadêmico conforme o [guia do Compose](devops-compose.md).
2. Copie `devops/monitoramento/.env.example` para `devops/.env.monitoramento`. Gere quatro senhas hexadecimais aleatórias de 64 caracteres, diferentes entre si e das credenciais da aplicação. Para um volume novo, preencha `MON_ZABBIX_INITIAL_PASSWORD` com a senha de fábrica do usuário `Admin`, descrita na [documentação do Zabbix](https://www.zabbix.com/documentation/7.0/en/manual/quickstart/login). O provisionamento usa esse valor para trocar a senha inicial. Depois, retire esse valor do arquivo local e guarde as quatro senhas com os volumes.
3. Execute os comandos abaixo na raiz. O primeiro build baixa as imagens e o plugin Zabbix do Grafana.

```powershell
$monitoramento = @('--env-file', 'devops/.env.academico', '--env-file', 'devops/.env.monitoramento',
    '-f', 'compose.devops.yml', '-f', 'compose.monitoramento.yml')
docker compose @monitoramento config --quiet
docker compose @monitoramento up -d --build --wait --wait-timeout 240 api grafana
```

## Acessar e demonstrar

- [Aplicação](http://localhost:18082), [Zabbix](http://localhost:18083) e [dashboard no Grafana](http://localhost:18084/d/relaxabarber-academico).
- Entre no Zabbix como `Admin` com `MON_ZABBIX_ADMIN_PASSWORD`. Abra **Monitoring → Hosts → RelaxaBarber API → Web** e confira os cenários.
- Entre no Grafana como `admin` com `MON_GRAFANA_ADMIN_PASSWORD`. Aguarde uma ou duas coletas para o painel receber dados.
- Para demonstrar indisponibilidade, execute `docker compose @monitoramento stop api`. Aguarde a próxima coleta, observe os dois cenários e restaure com `docker compose @monitoramento start api`.
- Para medir CPU e RAM dos contêineres neste host, use `docker compose @monitoramento stats --no-stream`. O painel histórico contém as sondas HTTP. Métricas do host físico e séries históricas de CPU/RAM dos contêineres ficam fora deste ambiente. A coleta não requer agente privilegiado nem acesso ao socket do Docker.

Uma amostra no Docker Desktop após a recuperação da API registrou 114 MiB para o Grafana, 49 MiB para a interface do Zabbix, 52 MiB para o servidor Zabbix e 179 MiB para o PostgreSQL do Zabbix. A pilha completa consumiu cerca de 559 MiB, incluindo os 165 MiB da aplicação e do banco acadêmico. A amostra exclui Docker Desktop, navegador e pico de build.

## Encerrar

Para parar somente o monitoramento, mantendo a aplicação acadêmica em execução:

```powershell
docker compose @monitoramento stop grafana zabbix-configurar zabbix-web zabbix-servidor zabbix-banco
```

Para encerrar toda a pilha acadêmica preservando os volumes, execute `docker compose @monitoramento down`.
