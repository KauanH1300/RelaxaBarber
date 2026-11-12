# Expediente semanal por filial — backend

GET `/filiais/{filial_id}/horarios` exige autenticação e acesso à filial ativa.
PUT no mesmo endereço exige ADMIN ativo, relido no banco, e substitui a semana
inteira em uma única transação. 0 = segunda-feira, 6 = domingo.

Exemplo de corpo PUT (dias fechados não possuem horários):

```json
{"dias":[
  {"dia_semana":0,"fechado":false,"hora_inicio":"09:00","hora_fim":"18:00"},
  {"dia_semana":1,"fechado":false,"hora_inicio":"09:00","hora_fim":"18:00"},
  {"dia_semana":2,"fechado":false,"hora_inicio":"09:00","hora_fim":"18:00"},
  {"dia_semana":3,"fechado":false,"hora_inicio":"09:00","hora_fim":"18:00"},
  {"dia_semana":4,"fechado":false,"hora_inicio":"09:00","hora_fim":"18:00"},
  {"dia_semana":5,"fechado":false,"hora_inicio":"09:00","hora_fim":"13:00"},
  {"dia_semana":6,"fechado":true}
]}
```

Este é apenas um exemplo de requisição; nenhum expediente padrão é gravado.
A resposta contém `filial_id`, `configurado` e `dias` ordenados. Filiais sem
configuração retornam `configurado: false, dias: []` e preservam temporariamente
a criação de reservas sem restrição semanal. Não há endpoint para remover a
configuração inteira. Uma semana com sete dias fechados significa fechamento.

Uma vez configurada, toda nova reserva deve caber integralmente no intervalo
do dia. Abertura e término exatamente no fechamento são permitidos. Horários
são locais, sem offset, no fuso America/Recife já adotado pelo projeto.
Não há turnos noturnos, almoço, feriados ou jornada individual nesta etapa.

PUT retorna 422 para payload inválido, 403 para falta de permissão/atividade,
404 para filial inexistente na gestão ADMIN, e 409 se alguma reserva pendente
ou aguardando ainda não terminou e ficaria fora da semana proposta. Isso inclui
a primeira configuração. Concluídos, cancelados e atendimentos já iniciados
não são alterados. Reservas e comandas nunca são reescritas por esta operação.

As escritas serializam pela linha da filial: UPDATE para configurar, SHARE
para agendar. A conferência de reservas ocorre depois do lock e antes de
substituir os sete registros. Configuração parcial causada por escrita direta
é recusada pelo serviço (não é interpretada como ausência de configuração).
As constraints garantem cada linha; a API garante a semana completa.

## Validação antes de disponibilizar

1. Executar de `backend`: `python -B -m pytest -p no:cacheprovider -q`.
   Essa suíte bloqueia banco externo e usa mocks/SQLite em memória.
2. A suíte `integration_tests` recria schema: executar apenas no PostgreSQL
   local descartável validado por sua fixture, nunca no Supabase. O teste
   `test_horarios_filial.py` cobre as duas ordens da disputa entre configurar
   expediente e criar reserva.
3. Revisar a DDL offline e a revisão `b91e4c7d203a`, posterior a
   `a15c39d42e68`. A migração cria apenas `public.filial_horarios`, sem backfill.
4. Após autorização específica para o banco real, planejar aplicação da migração
   antes de iniciar o backend novo: a criação de reservas passa a consultar a
   nova tabela mesmo quando ainda não há expediente configurado.
5. Validar GET/PUT por perfil, duas filiais com semanas distintas, dia fechado,
   reserva nos limites e conflito 409 preservando a configuração anterior.

Nenhuma migração é aplicada automaticamente por esta entrega. O downgrade
remove apenas a tabela nova e perde as configurações; não usar como rotina de
validação nem sem revisão e autorização próprias.
