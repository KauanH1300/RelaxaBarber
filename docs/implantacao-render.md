# Implantação em um serviço web no Render

O Dockerfile da raiz compila o React com Node 22 e serve o build pelo FastAPI
em Python 3.12. Selecione o runtime Docker, use a raiz do repositório como
contexto e deixe o Render fornecer `PORT`. O fallback local é `8000`.
O Docker Compose e os Dockerfiles em `frontend/` e `backend/` atendem ao desenvolvimento.

- Use a URL HTTPS pública do serviço em `BACKEND_CORS_ORIGINS`, como lista JSON de
  origens exatas, sem barra final. A mesma lista autoriza escritas do portal.
  Mantenha `CLIENT_PORTAL_COOKIE_SECURE=true`. Frontend e API compartilham a
  origem e os caminhos atuais. A navegação HTML nas rotas do React recebe o
  build. Os clientes da API recebem o formato habitual de cada endpoint.
- Configure `DATABASE_URL` para o papel de runtime do Supabase e `SECRET_KEY`
  como segredo estável. Use TLS `verify-full` com a CA oficial da conexão.
  Configure `connect_timeout` na URL para limitar espera de conexão.
- Defina `SUPABASE_URL`, `SUPABASE_STORAGE_BUCKET` e
  `SUPABASE_SERVICE_ROLE_KEY` somente no ambiente do serviço.
- Configure `CLIENT_PORTAL_SMTP_HOST`, `CLIENT_PORTAL_SMTP_PORT`,
  `CLIENT_PORTAL_SMTP_TLS`, `CLIENT_PORTAL_SMTP_FROM`,
  `CLIENT_PORTAL_SMTP_USER` e `CLIENT_PORTAL_SMTP_PASSWORD`.
  `CLIENT_PORTAL_SMTP_CA_FILE` é opcional. Verifique se o serviço
  consegue entregar pelo SMTP do Brevo com STARTTLS na porta 2525.
  As portas SMTP usuais são bloqueadas no Render Free.

## Banco e verificação

Execute o Alembic em uma etapa administrativa separada, com destino e revisão
previamente conferidos. O código desta entrega espera a revisão
`d5a812e4c970`. Inicializar o serviço não aplica migrações.

Configure `/health` como verificação de disponibilidade do processo no Render.
`/ready` consulta PostgreSQL e devolve 503 se falhar. Esse segundo endpoint
verifica conectividade, sem validar a revisão Alembic ou a disponibilidade de
Storage e SMTP.

Antes de liberar o ambiente, confira a sessão do portal em HTTPS, a entrega de
códigos pelo Brevo, os uploads no bucket e a resposta após a suspensão do
plano gratuito. Use os segredos de um ambiente separado para essa validação.

O build local usa `docker build -t relaxabarber-prod .`. Para rodar a imagem
localmente, forneça as variáveis por um arquivo de ambiente protegido fora do
repositório e mapeie a porta do contêiner somente para o loopback.
