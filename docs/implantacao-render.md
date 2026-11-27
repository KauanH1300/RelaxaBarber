# Publicação de QA em um serviço web no Render

Use também o [guia de segurança de produção](seguranca-producao.md) para configurar
os proxies confiáveis, as origens HTTPS e as verificações de publicação.

O Dockerfile da raiz compila o React com Node 22 e serve o build pelo FastAPI
em Python 3.12. Frontend e API compartilham a origem. O build da imagem define
`VITE_API_URL` vazio para usar caminhos relativos, e `FRONTEND_DIST` é definido
pela imagem. O processo escuta em `0.0.0.0` na porta fornecida pelo Render.
O TLS público termina no Render. Os Compose de desenvolvimento e acadêmico
continuam disponíveis para uso local.

## Variáveis para QA publicado

Configure no painel do serviço. Use credenciais exclusivas do QA, com valores
mantidos fora do repositório, do bundle do frontend e dos registros de teste.

| Provedor | Variável | Finalidade |
|---|---|---|
| Render | `PORT` | Porta do processo. O Render fornece o valor e a aplicação usa 8000 como fallback local. |
| Aplicação | `BACKEND_CORS_ORIGINS` | Lista JSON com a origem HTTPS exata do serviço, sem barra final. A mesma lista autoriza escritas no portal. |
| Aplicação | `CLIENT_PORTAL_COOKIE_SECURE` | Mantenha `true` para que o cookie de sessão do portal seja enviado por HTTPS. |
| Aplicação | `SECRET_KEY` | Segredo estável e exclusivo de QA para assinatura e proteção de sessões e desafios. Obrigatório na inicialização. |
| Supabase | `DATABASE_URL` | Conexão SQLAlchemy com o login restrito do QA. Use `sslmode=verify-full`, `sslrootcert` com a CA oficial e `connect_timeout`. Obrigatória na inicialização. |
| Supabase | `SUPABASE_URL`, `SUPABASE_STORAGE_BUCKET`, `SUPABASE_SERVICE_ROLE_KEY` | Origem do projeto, bucket e credencial de escrita no servidor para fotos da vitrine. O bucket de QA deve permitir leitura pública das fotos destinadas à vitrine. |
| Brevo | `CLIENT_PORTAL_SMTP_HOST`, `CLIENT_PORTAL_SMTP_PORT`, `CLIENT_PORTAL_SMTP_TLS` | Host do relay, porta `2525` e modo `starttls` no Render Free. |
| Brevo | `CLIENT_PORTAL_SMTP_FROM`, `CLIENT_PORTAL_SMTP_USER`, `CLIENT_PORTAL_SMTP_PASSWORD` | Remetente autorizado, login SMTP e chave SMTP. Necessários para validar ativação, recuperação e troca de e-mail. |
| Brevo | `CLIENT_PORTAL_SMTP_CA_FILE` | Opcional. Caminho para CA de SMTP específica, quando necessário. |

Para o PostgreSQL, confira o host e o login no painel do Supabase. Se precisar
de IPv4, use o Session Pooler. Disponibilize a CA como arquivo de runtime e
aponte `sslrootcert` para um caminho legível pelo usuário da imagem. No Render, o
caminho de arquivos adicionados como Secret Files é `/etc/secrets/<nome>`.
A imagem roda como UID/GID 10001. Se o arquivo estiver ilegível, ajuste a
forma de fornecer a CA antes de prosseguir e mantenha `verify-full`.

O cliente SMTP negocia STARTTLS e verifica o certificado antes de autenticar.
O Render Free bloqueia as portas SMTP 25, 465 e 587. A porta 2525 é suportada
pelo Brevo e a entrega a partir do Render deve ser testada após a publicação.

[Arquivos de runtime no Render](https://render.com/docs/docker-secrets) ·
[TLS no PostgreSQL Supabase](https://supabase.com/docs/guides/platform/ssl-enforcement) ·
[SMTP do Brevo](https://help.brevo.com/hc/en-us/articles/10905415650322-Which-SMTP-port-should-I-use-Port-587-465-or-2525)

## Checklist de publicação manual

1. **Supabase Free.** Separe um projeto de QA com dados fictícios. Confirme o
   destino e a revisão Alembic antes de qualquer escrita. Prepare o grupo
   `relaxabarber_runtime` e o login restrito conforme o
   [guia de segurança](seguranca-horarios-filial.md). Prepare o esquema com
   a identidade administrativa em uma etapa separada. A ponta ao preparar este
   guia é `7d8e3c42fa91`, posterior a `d5a812e4c970` e `2eb4a16d930c`.
   Confirme a ponta do commit que será publicado e a revisão efetivamente
   aplicada. Prepare uma filial e uma conta ADMIN fictícias para a primeira
   sessão. O preparo acadêmico é restrito ao Compose local.
2. **Supabase Storage e Brevo Free.** Prepare um bucket exclusivo para as fotos
   fictícias da vitrine. Autorize um remetente para o QA no Brevo e confirme
   que o domínio e a cota disponíveis atendem ao teste.
3. **Render Free.** Quando a publicação for autorizada, selecione a
   `develop` no Web Service Docker, mantenha a raiz como contexto e use o
   subdomínio padrão `onrender.com`. Defina as variáveis acima antes do primeiro
   deploy e configure `/health` como verificação de saúde. A inicialização
   não aplica migrações. Depois do deploy, confirme o commit publicado e
   verifique `/health` e `/ready`. O segundo endpoint confirma conectividade
   com o banco, sem conferir a revisão Alembic ou as integrações.
4. **Validar RNF05.** Confira certificado e redirecionamento HTTP para HTTPS.
   No navegador, faça login e confira chamadas da interface à API via HTTPS,
   ausência de conteúdo misto e atributo `Secure` no cookie do portal.
   Use login e dados fictícios. Valide também a entrega de um código de e-mail
   e o upload e leitura de uma foto na vitrine.
5. **Validar RNF11.** Registre os planos ativos, as cotas e a cobrança exibida
   nos painéis do Render, Supabase e Brevo. Confira complementos e meios de
   pagamento antes de habilitar qualquer serviço. Use o subdomínio gratuito
   e registre também a retomada após inatividade. Para o aceite, confirme
   como a exigência de tecnologias open-source se aplica aos serviços
   gerenciados externos.

Os requisitos permanecem sem evidência de publicação até essas verificações.
O Render Free pode suspender por inatividade ou por cota, e excedentes podem
gerar cobrança se houver meio de pagamento vinculado. Confira os limites e
uso dos três serviços no momento da validação.

[Render Free](https://render.com/docs/free) ·
[TLS no Render](https://render.com/docs/tls) ·
[Supabase Free](https://supabase.com/pricing) ·
[Brevo Free](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan)
