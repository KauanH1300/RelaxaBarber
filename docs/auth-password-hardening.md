# Reforço de senhas, etapa 1

## Política aprovada

Novas senhas de clientes exigem 8 a 128 caracteres Unicode. Equipe exige 15 a 128.
Espaços são preservados e não existem regras obrigatórias de composição.
A validação é aplicada a cadastro, troca e redefinição, no servidor e nos formulários ativos.
O login continua aceitando senhas antigas, inclusive curtas ou presentes na blocklist.

O mínimo de 8 para clientes é uma flexibilização consciente da recomendação de 15 do
NIST SP 800-63B-4 para senha como fator único. É uma decisão de usabilidade aprovada
para o portal. Rate limiting, blocklist e orientação ajudam a reduzir o risco, mas
não tornam a política equivalente à recomendação. Equipe segue o mínimo de 15.
Referência https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver

## Hash e capacidade

Argon2id usa 65536 KiB, time_cost 3, parallelism 4, salt 16 bytes, saída 32 bytes.
Hashes novos usam salt aleatório. Login válido atualiza hashes com parâmetros antigos,
na transação de autenticação, sem exigir mudança de senha ou revogar a sessão por rehash.
A recuperação da equipe vinculada ao hash antigo deixa de ser elegível após rehash.

Há um semáforo por processo para uma operação Argon2 de cada vez, incluindo geração,
verificação e rehash. Saturação retorna HTTP 503 e Retry-After de 2 segundos.
Não há fila ilimitada de verificações esperando memória. Cada worker pode consumir
aproximadamente 64 MiB adicionais durante Argon2, além de Python e bibliotecas.
O limite é por processo. Configurar um worker inicialmente em contêiner de 512 MiB.
Aumentar workers multiplica o teto de memória. Medir novamente no hardware de produção.

## Limites persistidos

Reutiliza portal_limites, com transações e SELECT FOR UPDATE.
Login da equipe tem 30 admissões por IP e 5 por conta em janela fixa de 900 segundos.
Troca autenticada usa a mesma quantidade, com finalidade distinta e ID do usuário.
Os contadores são confirmados antes da verificação para que falhas não desfaçam o limite.
Os dois buckets são contabilizados, inclusive quando um já está esgotado.
Os limites dos clientes permanecem os mesmos.
Contas inexistentes passam por hash fictício. Falha, conta inativa e senha errada
retornam a mesma mensagem de credenciais inválidas. Limites expiram automaticamente.
Um atacante ainda pode consumir temporariamente a cota de uma conta conhecida.
Configurar o proxy para fornecer IP real apenas por encaminhadores confiáveis.

## Blocklist local e licença

Arquivo backend/app/core/senhas_comuns.txt versionado no Git.
Fonte SecLists, Passwords/Common-Credentials/10k-most-common.txt.
Obtido de https://github.com/danielmiessler/SecLists em 26/11/2026.
Fonte de senhas comuns e observadas em credenciais, sem garantia de cobertura de
todos os vazamentos. Licença MIT de Daniel Miessler preservada ao lado em
senhas_comuns.LICENSE. A lista original recebeu entradas locais de sequências e
nomes previsíveis da barbearia. Novas entradas devem ser revisadas e versionadas.
Comparação da senha inteira com casefold, sem retirar espaços ou procurar substrings.
Nenhuma senha é enviada a serviços externos.

## Interface e operação

zxcvbn-ts executa localmente no navegador com dicionários comum e inglês e termos da
barbearia. A estimativa é informativa. O backend decide comprimento e blocklist.
Os formulários permitem mostrar/ocultar senha e explicam frases-senha e comprimento.
Dicionário português não está incluído. A estimativa para frases em português é limitada.

Sem migração de banco. Reutiliza as tabelas existentes de limites e sessões.
Requer atualizar a imagem da API e instalar o lockfile do frontend.
O frontend só envia senhas nos endpoints de autenticação existentes.
A branch parte da develop e não inclui alterações visuais pendentes em outra worktree.


## Medição local

Docker com 512 MiB e 1 CPU, senha fictícia: uma geração e três verificações em
1,355 segundo, pico RSS de 107,5 MiB para o processo. Resultado local, variável
conforme carga e hardware. Não substitui medição no ambiente publicado.

SHA-256 da blocklist distribuída: 5224bdadaa374459794f9f4269e5123e2b036cc3d12b59fd64017abd751a8459.

## Validação

Testes unitários cobrem fronteiras Unicode, blocklist sem substrings, preservação de
espaços, parâmetros/salt do Argon2, rehash de hash antigo e saturação concorrente.
Testes PostgreSQL cobrem contadores atômicos, expiração, finalidades independentes,
rehash de clientes e equipe com senha antiga curta, quatro perfis, códigos e revogação.
Regressão do portal e troca de e-mail: 42 casos passaram. Cinco casos de troca de
e-mail falharam também na develop sem alterações (dois de duplicidade e três de
fixture de sessão da equipe com chave estrangeira). Não foram alterados nesta etapa.
Build TypeScript/Vite e validação no Edge de comprimento, mostrar/ocultar e indicador.
