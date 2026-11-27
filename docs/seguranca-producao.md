# Segurança de produção no Render e na AWS

Use o Dockerfile da raiz para servir o React e a API pela mesma origem. O processo roda como UID/GID 10001 e escuta na porta indicada por `PORT`. As portas dos Compose de desenvolvimento ficam no loopback. O ambiente local usa `ENV=development` e conserva HTTP e a documentação interativa.

## Configuração comum

| Configuração | Valor no ambiente publicado |
| --- | --- |
| `ENV` | `production`. O FastAPI roda com debug desativado. Swagger, ReDoc e OpenAPI ficam indisponíveis. |
| `BACKEND_CORS_ORIGINS` | Lista JSON com as origens HTTPS exatas e os hosts públicos servidos, sem barra final. Use apenas os domínios realmente publicados. A lista também valida a origem do CSRF da equipe e das escritas do portal. |
| `BACKEND_TRUSTED_PROXY_CIDRS` | IPs ou CIDRs exatos dos proxies confirmados, separados por vírgula. Deixe vazio se houver TLS direto. Os valores da plataforma precisam ser confirmados antes da publicação. |
| `TEAM_COOKIE_SAMESITE` | Use `lax` na mesma origem. O portal mantém `SameSite=Strict`. Os cookies da equipe e do portal são HttpOnly e Secure no ambiente publicado, inclusive se `CLIENT_PORTAL_COOKIE_SECURE=false` estiver configurado. |
| `SECRET_KEY` | Use pelo menos 32 bytes aleatórios exclusivos por ambiente, gerados de forma criptograficamente segura. A rotação invalida sessões, dispositivos e códigos e deve ser planejada. |
| `DATABASE_URL` | PostgreSQL com login da aplicação de privilégio mínimo e `sslmode=verify-full`. Forneça a CA do provedor por `sslrootcert` ou `PGSSLROOTCERT`. A aplicação e o Alembic exigem verificação do host e recusam conexões sem TLS. Reserve a identidade de migração para o Alembic. |
| SMTP | Use `CLIENT_PORTAL_SMTP_TLS=ssl` ou `starttls` com a porta do relay e credenciais autorizadas. O cliente verifica a CA e o hostname antes de autenticar ou enviar. Para CA privada, use `CLIENT_PORTAL_SMTP_CA_FILE`. |
| `SUPABASE_URL` e credencial de Storage | Use a origem HTTPS exata. A CSP autoriza essa origem para imagens públicas da vitrine. Mantenha a credencial de escrita no servidor. |

Forneça credenciais e arquivos privados ao contêiner no runtime. A imagem e o bundle React devem conter apenas código e configuração pública. Em ambientes com montagem de segredos, garanta que os arquivos estejam legíveis pelo UID 10001. Use `python -m app` para iniciar o servidor com o processamento automático de proxy do Uvicorn desligado. O aplicativo usa o IP do socket como ponto de partida e percorre `X-Forwarded-For` da direita para a esquerda até o primeiro salto fora dos CIDRs confiáveis. Cabeçalhos de um peer não confiável não alteram o IP nem o protocolo. Limite o acesso direto ao contêiner e confirme que cada proxy confiável acrescenta ou sobrescreve os valores de forma controlada.

A borda deve redirecionar HTTP para HTTPS. A aplicação recusa HTTP para as rotas do site e da API, exceto sondas internas GET/HEAD em `/health` e `/ready` vindas de loopback ou dos peers autorizados. HSTS, CSP, nosniff, Referrer-Policy e proteção contra framing são enviados pela aplicação. A CSP autoriza os recursos de fontes, mapa e vitrine usados hoje e restringe scripts à própria origem. Logs de acesso do Uvicorn ficam desligados no ambiente publicado. Nos logs da borda e em ferramentas de observabilidade já disponíveis, evite registrar corpos, cookies, Authorization e parâmetros que carreguem credenciais.

## Render

- Configure o Web Service Docker com o Dockerfile da raiz. O Render termina o TLS e redireciona HTTP para HTTPS. Configure o domínio escolhido em `BACKEND_CORS_ORIGINS` e desabilite o subdomínio padrão caso não faça parte do acesso público. [Web Services](https://render.com/docs/web-services) · [TLS no Render](https://render.com/docs/tls)
- Comece pelos passos de variáveis, Secret Files e SMTP do [guia Render](implantacao-render.md). Confirme os peers de entrada e os saltos do balanceador, incluindo como são anexados `X-Forwarded-For` e `X-Forwarded-Proto`. Os CIDRs de saída da plataforma têm outra finalidade. Se a cadeia não puder ser confirmada e testada contra cabeçalhos falsificados, mantenha a publicação pendente. [IP do cliente no Render](https://render.com/articles/how-render-handles-ddos-attacks) · [IPs de saída](https://render.com/docs/outbound-ip-addresses)
- Configure a sonda em `/health` e confirme `/ready` via HTTPS. Verifique o acesso do serviço à porta TLS do SMTP do relay escolhido. [Guia de SMTP do Brevo](https://help.brevo.com/hc/en-us/articles/10905415650322-Which-SMTP-port-should-I-use-Port-587-465-or-2525)

## AWS

- Se já houver um Application Load Balancer, use certificado no listener HTTPS 443 e configure o listener 80 somente para redirecionar. Limite o security group da aplicação a conexões do security group do balanceador na porta interna do processo. Mantenha banco e contêiner sem acesso público direto e autorize no banco apenas origens da aplicação e da manutenção. Com ALB, mantenha `X-Forwarded-For` em modo `append` e a inclusão da porta do cliente desligada. Configure os CIDRs confirmados do balanceador e, se houver mais proxies, valide toda a cadeia antes da abertura ao público. [Cabeçalhos do ALB](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/x-forwarded-headers.html)
- Use o mecanismo de injeção de segredos já disponível no ambiente AWS, com identidade e permissões restritas para a aplicação. Forneça a CA do PostgreSQL do provedor e limite as conexões de saída necessárias para banco, storage e SMTP. [Verificação TLS do PostgreSQL](https://www.postgresql.org/docs/17/libpq-ssl.html)

## Verificações

O PR #103 já cobriu confirmação e verificação por e-mail, concorrência, expiração, reenvio, confiança, revogação, recuperação e isolamento de perfis no Supabase de TESTES. Na etapa 5, a suíte `backend/tests/test_entrada_producao.py` usa ASGI, build React e dados fictícios para validar HTTP/HTTPS, proxy, HSTS, CSP, documentação desativada, CORS/CSRF, cookies, erros sanitizados e parâmetros TLS. Um PostgreSQL descartável confirmou TLS real e a recusa de hostname divergente. O transporte SMTP é simulado para verificar a ordem de STARTTLS e a validação do certificado.

Após autorização para publicar, valide certificado e redirecionamento na borda real, IP recebido por meio do proxy, sondas, segurança de rede, TLS do banco, entrega SMTP real e o fluxo de 2FA com conta de teste. No navegador, confira a landing, fontes, mapas, vitrine, agendamento, portal e painel. Confirme antes a revisão Alembic do destino, incluindo `5ce84d69be21` em ambientes que ainda não receberam a etapa 4. A etapa 5 não adiciona migrações.
