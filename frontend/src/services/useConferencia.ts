import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { contextoAtual, contextoValido } from './filialAtiva';

export function useConferencia() {
  const [consultando, setConsultando] = useState(false);
  const [aviso, setAviso] = useState('');
  const trava = useRef(false);
  const montado = useRef(false);
  useEffect(() => { montado.current = true; return () => { montado.current = false; }; }, []);

  async function conferir<T>(consultar: () => Promise<T>, confirmado: (dados: T) => boolean) {
    if (trava.current) return;
    const contexto = contextoAtual();
    trava.current = true;
    setConsultando(true);
    setAviso('');
    try {
      const dados = await consultar();
      if (montado.current && contextoValido(contexto) && !confirmado(dados)) {
        setAviso('Os dados consultados ainda não confirmam a operação. Seu rascunho foi mantido.');
      }
    } catch (erro) {
      if (montado.current && contextoValido(contexto)) {
        setAviso(axios.isAxiosError(erro) && erro.response?.status === 404
          ? 'A operação ainda não foi localizada. O resultado continua incerto.'
          : 'Não foi possível conferir agora. Tente consultar novamente.');
      }
    } finally {
      trava.current = false;
      setConsultando(false);
    }
  }
  return { conferir, consultando, aviso };
}
