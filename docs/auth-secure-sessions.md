# Sessões seguras da equipe

Branch isolada a partir de develop eddd502 (primeira etapa de senhas integrada).

A equipe autentica exclusivamente pelo cookie HttpOnly de JWT, com validade de 60 minutos e consulta da sessão revogável no PostgreSQL. Login retorna apenas mensagem. Bearer não é aceito, e JWT sem transport=cookie-v1 é rejeitado inclusive quando copiado para cookie. A implantação exige novo login das sessões antigas; não há fallback. A aplicação remove a antiga chave token de localStorage e sessionStorage. O identificador em memória usado pelo contexto de filial representa apenas uma geração local para descartar respostas antigas; não autoriza nenhuma chamada.

CSRF: POST /auth/csrf valida Origin pela lista explícita BACKEND_CORS_ORIGINS, retorna assinatura HMAC com domínio exclusivo da equipe e mantém o segredo de base em cookie HttpOnly. A assinatura fica ligada ao JWT autenticado ou a um segredo anônimo aleatório anterior ao login. Toda escrita autenticada exige origem permitida e X-Equipe-CSRF válido; login, recuperação e redefinição também exigem ambos. Nenhum segredo de sessão é retornado ao JavaScript. Respostas de autenticação e bootstrap são no-store. CORS sozinho não substitui essas verificações.

Configuração:
- Produção/Render/AWS: ENV=production (ou ausente), HTTPS, cookie Secure com prefixo __Host-, Path=/, sem Domain. Todos os workers devem compartilhar SECRET_KEY.
- Mesmo site/origem: TEAM_COOKIE_SAMESITE=lax (padrão). Para frontend/API em sites distintos: none, exclusivamente HTTPS. Navegadores podem bloquear cookies de terceiros; preferir domínio próprio no mesmo site ou proxy de mesma origem.
- HTTP local/Docker: definir ENV=development explicitamente; usar o mesmo host no frontend/API (127.0.0.1 em ambos ou localhost em ambos). Não usar essa configuração em ambiente publicado.
- BACKEND_CORS_ORIGINS deve conter origens completas exatas do frontend, incluindo a origem de produção; nunca curinga. Axios usa withCredentials. Nenhuma alteração nas permiss?es dos quatro perfis.
- Sessão do cliente mantém cookie, caminho e servi?os próprios. A equipe ignora o cookie do cliente, e o portal ignora o da equipe.

Sem migração de banco: reutiliza equipe_sessoes. Publicar frontend e backend juntos; tokens anteriores deixam de autenticar. Sessões antigas persistidas expiram pela limpeza existente. Revoga??o no logout e após alteração/redefinição continua usando o servi?o atual. Abas abertas detectam revogação na próxima chamada autenticada.

Validação: seis cenários PostgreSQL descartável aprovados (quatro perfis, logout, expiração, CSRF, rejeição de Bearer e JWT antigo, isolamento, troca de senha); teste adicional de redefinição por código aprovado (1 passed) comprovou revogação. Edge real com API simulada aprovou login, HttpOnly, limpeza dos dois storages, restauração após reload e logout; nenhuma requisição enviou Authorization. Build TypeScript/Vite aprovado. Os testes legados que esperam access_token no login ou enviam Bearer precisam adotar o novo contrato de cookie; não são fallback suportado. As cinco falhas anteriores documentadas na etapa de senhas não foram reexecutadas. npm ci relatou 13 avisos de dependências (9 moderate, 4 high); dependências não foram modificadas nesta etapa.

Homologação real aprovada no Edge com frontend compilado e API da branch em porta 8001, Supabase de testes autorizado: login e restauração 200, cookie HttpOnly confirmado pelo navegador, PATCH autenticado 200, mesmo PATCH sem CSRF 403, portal sem autenticação de cliente 401, logout 204. Conta temporária e sessões removidas ao final. Nenhuma migração. O ambiente isolado carrega o .env com uvicorn --env-file (dotenv); docker --env-file não interpreta as aspas presentes na URL e causa erro antes da conexão. Credenciais e scripts locais de QA não fazem parte do commit.
