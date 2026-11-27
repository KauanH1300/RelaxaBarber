# Confirmação de e-mail da equipe

Aplique `alembic upgrade head` com a credencial de migração. A revisão `3bf126fd81a0` registra a confirmação e a finalidade dos desafios. Todo e-mail da equipe começa pendente. Valide o SMTP e o acesso à caixa postal de pelo menos um administrador antes de liberar a versão. O fluxo mantém o cadastro feito pelo administrador.

## Funcionário sem e-mail confirmado

Um administrador com e-mail confirmado identifica o funcionário por um canal interno, registra o motivo e usa **Recuperar acesso** em **Funcionários** ou `POST /usuarios/{usuario_id}/recuperacao-administrativa` com a própria senha em `senha_atual_admin` e uma nova senha em `senha`. A operação revoga as sessões, invalida os códigos e grava o responsável, a conta, a data e o motivo na mesma transação. Entregue a nova senha por canal interno seguro e oriente a pessoa a alterá-la em **Meu perfil → Alterar senha** assim que recuperar o acesso. Evite incluir dados pessoais, senhas ou códigos no campo `motivo`.

## Administrador sem acesso à caixa postal

1. Se houver outro administrador com e-mail confirmado, ele pode atualizar o endereço para uma caixa corporativa sob controle do titular após confirmar sua identidade por um canal independente. O titular entra com sua senha e confirma o novo endereço com o código.
2. Se não houver administrador disponível, o responsável autorizado pela infraestrutura abre um chamado restrito e valida a identidade do titular e a titularidade da nova caixa. Use uma credencial de manutenção e confirme diretamente no banco o UUID da conta, o perfil administrativo e a unicidade do novo endereço.
3. Em uma única transação, bloqueie a linha da conta, atualize o endereço em `usuarios`, mantenha `email_confirmado_em` nulo, marque os desafios abertos em `equipe_recuperacoes` como consumidos e revogue as sessões em `equipe_sessoes`. Se também for necessário trocar a senha, use o hash produzido por `app.core.security.hash_senha` para uma senha forte entregue por canal interno seguro. Registre operador, UUID, data, motivo e referência do chamado no log de manutenção. Preserve a trilha de auditoria no sistema de chamados.
4. O administrador entra e confirma o novo endereço pelo fluxo normal. Revogue o acesso temporário à infraestrutura e encerre o chamado após validar o painel.

Se a única conta administrativa tiver perdido tanto a senha quanto a caixa postal, use o procedimento de infraestrutura. O estado de confirmação depende da validação do código enviado à nova caixa.
