export const EVENTO_ESTOQUE_ATUALIZADO = 'relaxabarber:estoque-atualizado';

export function podeAlterarEstoque(url: string | undefined, metodo: string | undefined) {
  return !!metodo && ['post', 'put', 'patch', 'delete'].includes(metodo) &&
    /^\/(?:agendamentos|comandas|estoque\/produtos)(?:\/|\?|$)/.test(url ?? '');
}
