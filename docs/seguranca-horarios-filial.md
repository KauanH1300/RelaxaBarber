# Segurança de expediente por filial

Revisão `c82f6a1d904b`, posterior a `b91e4c7d203a`. A migração original permanece
intacta. Esta entrega não autoriza aplicar nenhuma revisão no Supabase real.

## Papéis e permissões

O migrador/proprietário administra schema, constraints, extensão e policies.
O runtime não deve possuir objetos, SUPERUSER, BYPASSRLS, CREATEDB ou CREATEROLE.
`relaxabarber_runtime` é o grupo de privilégios; um login separado herda esse
grupo. Não usar `postgres` como identidade cotidiana do backend.

Na nova tabela, o runtime recebe somente SELECT, INSERT e DELETE. O serviço
substitui a semana por DELETE + INSERT dentro da transação e lock da filial.
UPDATE, TRUNCATE, REFERENCES, TRIGGER e administração da tabela não são necessários.
IDs são UUIDs gerados pela aplicação; não existem sequences de runtime nesse fluxo.

A migração habilita RLS e cria apenas três policies, todas para o grupo runtime:
SELECT USING (true), INSERT WITH CHECK (true), DELETE USING (true). Não existe
policy UPDATE nem dependência de auth.uid(). Os JWTs do FastAPI não são
automaticamente transmitidos como identidade PostgreSQL.

As policies autorizam o backend, não distinguem ADMIN nem filiais. Esses controles,
a exigência dos sete dias e a conferência de reservas continuam no FastAPI.
Credenciais comprometidas do runtime ainda permitiriam ignorar essas regras.
Não há mudança de RLS nas outras onze tabelas nesta revisão.

## Default privileges e acesso externo

A migração revoga grants de tabela e coluna de PUBLIC, anon, authenticated,
service_role e do próprio runtime, antes de conceder a lista mínima. Isso remove
concessões já materializadas pelos defaults do criador sem alterar defaults
globais ou grants de outras tabelas. BYPASSRLS não substitui a necessidade de ACL:
service_role também deve ficar sem acesso à tabela.

Os papéis externos ausentes são ignorados, mas a ausência do runtime aborta a
migração. SUPERUSER/BYPASSRLS no runtime e privilégios herdados incompatíveis
também provocam falha. Não corrigir automaticamente memberships para passar:
revisar o provisionamento em uma etapa autorizada.

## Implantação futura

1. Revisar e provisionar os papéis fora da migração. A migração não cria logins
   ou senhas e não troca DATABASE_URL.
2. Confirmar identidade do projeto e revisão atual; obter backup e validar sua
   restauração em ambiente separado antes de autorizar a aplicação real.
3. Aplicar a criação da tabela e a segurança na mesma transação PostgreSQL,
   sem publicar o backend na revisão intermediária. Se a segurança falhar,
   reverter a transação inteira. Não usar stamp como substituto da migração.
4. Verificar proprietário, policies, grants efetivos, memberships e privilégios
   por coluna. Confirmar ausência de exposição indireta por RPC/views/Data API.
5. Só depois dos testes locais e de autorização específica, planejar a troca
   para login restrito. As credenciais reais não são parte desta entrega.

Os locks FOR SHARE/FOR UPDATE exigem SELECT e UPDATE em pelo menos uma coluna
das tabelas bloqueadas. Os testes reproduzem os grants auditados, incluindo os
grants de UPDATE(id) para usuarios e empresas. Estes permitem tentar alterar IDs
e merecem revisão futura; a migração atual não modifica essas tabelas.

## Downgrade conservador

O downgrade remove as três policies e revoga SELECT/INSERT/DELETE do runtime.
Mantém a tabela, seus dados, RLS habilitada e as revogações dos papéis externos.
Não restaura grants anteriores desconhecidos. O expediente para de funcionar
para o runtime até novo upgrade ou outra ação expressamente autorizada.
Não utilizar downgrade como rollback automático do backend. Um downgrade também
da revisão original elimina a tabela e suas configurações.

## Testes exclusivamente locais

`integration_tests/conftest.py` valida o destino exclusivo 127.0.0.1:55432 e a
identidade do banco/usuário antes do provisionamento. `runtime_roles.py` contém
DDL e grants somente para a base descartável: migrador sem login, grupo runtime,
login restrito, papéis da API e um login-probe sem herança para simular SET ROLE
da Data API. Nenhum desses comandos faz parte da migração de produção.

O schema é recriado por teste e a cadeia Alembic é aplicada como o migrador,
com defaults deliberadamente amplos para testar as revogações. As onze tabelas
legadas recebem no ambiente de teste os grants restritos auditados. Os serviços
e os nove cenários concorrentes abrem conexões como relaxabarber_dev_app, não
como superusuário. Os dados e hashes usados são inteiramente fictícios.

Somente executar após comprovar container recém-criado, PostgreSQL 17, rede none,
nenhuma porta publicada, armazenamento tmpfs e URL de testes exclusivamente local.
Nunca usar docker-compose.yml da aplicação: ele carrega o .env real.

Com as verificações concluídas e o executor compartilhando apenas o namespace
de rede do container descartável, executar de backend:

```
python -B -m pytest -p no:cacheprovider -q integration_tests/test_seguranca_horarios.py integration_tests/test_horarios_filial.py
```

A negação de DDL cobre o schema persistente public e a tabela. Não implica que
o login não possua TEMP no banco; ACLs do banco e de outros schemas exigem revisão
própria. Testes diretos de PostgreSQL não equivalem a testar a Data API HTTP real.
