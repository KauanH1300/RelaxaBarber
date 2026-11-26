import { ZxcvbnFactory } from '@zxcvbn-ts/core';
import * as comum from '@zxcvbn-ts/language-common';
import * as ingles from '@zxcvbn-ts/language-en';

const estimador = new ZxcvbnFactory({
  graphs: comum.adjacencyGraphs,
  dictionary: { ...comum.dictionary, ...ingles.dictionary, userInputs: ['relaxabarber', 'relaxaobigode'] },
});
const niveis = ['Muito fraca', 'Fraca', 'Razoável', 'Boa', 'Forte'];

export default function ForcaSenha({ senha }: { senha: string }) {
  const forca = estimador.check(senha.slice(0, 128)).score;
  return <div>
    <meter min={0} max={4} value={forca} aria-label="Força estimada da senha" />
    <small> Força estimada · {niveis[forca]}. Esta indicação é informativa.</small>
  </div>;
}
