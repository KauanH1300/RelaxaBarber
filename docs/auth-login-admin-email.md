# Verificação em duas etapas por e-mail para ADMIN

O login de um ADMIN exige senha e código de e-mail, salvo quando a senha é válida e o navegador apresenta um dispositivo confiável dentro da validade. Os demais perfis da equipe e o portal de clientes seguem com seus fluxos atuais. O desafio temporário só serve para verificar ou reenviar o código. A API administrativa exige uma sessão emitida após a verificação ou a validação do dispositivo confiável, inclusive para contas que já estavam autenticadas antes da implantação.

Para um ADMIN com e-mail pendente, o primeiro código válido também confirma a titularidade do endereço. A confirmação e a emissão da sessão acontecem na mesma transação. Falhas de SMTP impedem a ativação do código e exigem uma nova tentativa de login após o intervalo de envio.

## Prazos e dispositivos

- Cada código contém seis dígitos e vence em cinco minutos. O desafio dura até 15 minutos após a senha e aceita cinco tentativas no total, inclusive após reenvios. O reenvio pode ser solicitado após 60 segundos e invalida o código anterior. O servidor limita envios por conta e origem e tentativas de verificação por origem.
- Confiar neste dispositivo é opcional e começa desmarcado. A confiança vence em 30 dias contados da concessão, sem renovação automática em logins subsequentes. O cookie é HttpOnly e Secure em produção. O banco guarda apenas o HMAC do token.
- Em **Meu perfil → Segurança**, o ADMIN pode consultar e revogar um dispositivo ou todos. A revogação volta a exigir o código no próximo login. Sessões que já estavam abertas continuam sujeitas ao seu prazo normal. Alterações de senha, recuperação, mudança de e-mail, perfil, ativação ou vínculo administrativo revogam também as sessões e os desafios pendentes.
- A confiança reside no navegador que recebeu o cookie. Evite habilitá-la em computadores compartilhados. Limpar cookies ou usar outro perfil de navegador volta a exigir o código.

## Limitações e recuperação administrativa

O e-mail é vulnerável a phishing em tempo real, atraso de entrega e comprometimento da caixa postal. Se essa mesma caixa também permite recuperar a senha, uma invasão do e-mail pode comprometer as duas etapas. O sistema depende do SMTP e do acesso à caixa do ADMIN quando um dispositivo válido está indisponível.

Se houver outro ADMIN com acesso, ele deve verificar a identidade do titular por canal independente e atualizar o endereço para uma caixa sob controle do titular. O titular usa a senha e o código enviado ao novo endereço. A recuperação administrativa de funcionários sem e-mail confirmado continua seguindo o [procedimento anterior](auth-confirmacao-email.md).

Para o último ADMIN sem acesso à caixa, use o procedimento restrito de infraestrutura da mesma documentação. Identifique o UUID e confirme perfil, titularidade e unicidade do novo endereço. Na mesma transação de manutenção, bloqueie o usuário, atualize o e-mail com `email_confirmado_em = NULL`, invalide os desafios de `equipe_recuperacoes`, revogue as sessões em `equipe_sessoes` e remova todos os dispositivos do UUID de `equipe_dispositivos_confiaveis`. Se a senha também tiver sido perdida, aplique o procedimento de senha temporária forte e entrega por canal interno seguro. Registre o operador, a conta, o motivo e a referência em chamado restrito. Após a manutenção, o titular precisa passar pelo login com senha e código na nova caixa. O fluxo público de recuperação por e-mail mantém sua regra de elegibilidade e não emite uma sessão administrativa.

## Banco e homologação

A revisão `5ce84d69be21` parte de `3bf126fd81a0`. Aplique a migração com a credencial de migração antes de disponibilizar a nova API. Mantenha o SMTP e as origens do frontend configurados. Sessões ADMIN anteriores ao marcador de verificação precisarão autenticar-se novamente.

O roteiro `backend/integration_tests/homologacao_login_admin.py` exige o Supabase de TESTES já migrado e usa contas fictícias. O roteiro exercita os endpoints HTTP, consulta separadamente os privilégios do papel de aplicação, captura os códigos em memória e remove as contas usadas ao final. A entrega real pode ser homologada pelo navegador com uma conta ADMIN de TESTES e uma caixa postal autorizada.
