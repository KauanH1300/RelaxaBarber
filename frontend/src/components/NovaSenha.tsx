import { lazy, Suspense, useId, useState } from 'react';
const ForcaSenha = lazy(() => import('./ForcaSenha'));

export function NovaSenha({ valor, alterar, minimo, rotulo = 'Nova senha', confirmar = false }: {
  valor: string;
  alterar: (senha: string) => void;
  minimo: 8 | 15;
  rotulo?: string;
  confirmar?: boolean;
}) {
  const id = useId();
  const [visivel, setVisivel] = useState(false);
  const tamanho = Array.from(valor).length;
  return <div className="grid gap-2">
    <label htmlFor={id}>{rotulo}</label>
    <input id={id} type={visivel ? 'text' : 'password'} autoComplete="new-password" required
      aria-describedby={id + '-orientacao'} value={valor}
      onChange={evento => alterar(evento.target.value)}
      onInvalid={evento => evento.currentTarget.setCustomValidity('Informe uma senha de ' + minimo + ' a 128 caracteres.')}
      onInput={evento => {
        const comprimento = Array.from(evento.currentTarget.value).length;
        evento.currentTarget.setCustomValidity(comprimento < minimo || comprimento > 128
          ? 'Use de ' + minimo + ' a 128 caracteres.' : '');
      }}
      ref={elemento => {
        elemento?.setCustomValidity(tamanho < minimo || tamanho > 128 ? 'Use de ' + minimo + ' a 128 caracteres.' : '');
      }} />
    <button type="button" aria-controls={id} aria-pressed={visivel}
      onClick={() => setVisivel(!visivel)}>{visivel ? 'Ocultar senha' : 'Mostrar senha'}</button>
    <small id={id + '-orientacao'}>Use de {minimo} a 128 caracteres. Espaços e frases são permitidos.
      Escolha uma senha única e evite sequências conhecidas.</small>
    {!confirmar && valor && <Suspense fallback={<small>Calculando força…</small>}><ForcaSenha senha={valor} /></Suspense>}
  </div>;
}
