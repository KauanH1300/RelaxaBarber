const fuso = 'America/Recife';
const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

export function diaLocal() {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: fuso }).format(new Date());
}

export function dinheiro(valor: string | null) {
  return valor === null ? '—' : brl.format(Number(valor));
}

