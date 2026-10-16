export function dataLocal(data: Date): string {
  return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, '0')}-${String(data.getDate()).padStart(2, '0')}`;
}

export function horariosAgenda(inicios: string[]): string[] {
  // Mantém a grade provisória e acrescenta os blocos das reservas fora dela.
  const minutos = new Set(Array.from({ length: 21 }, (_, i) => 8 * 60 + i * 30));
  for (const inicio of inicios) {
    const [hora, minuto] = inicio.split(':').map(Number);
    if (Number.isInteger(hora) && Number.isInteger(minuto) && hora >= 0 && hora < 24 && minuto >= 0 && minuto < 60) {
      minutos.add(Math.floor((hora * 60 + minuto) / 30) * 30);
    }
  }
  return [...minutos].sort((a, b) => a - b).map((valor) => `${String(Math.floor(valor / 60)).padStart(2, '0')}:${String(valor % 60).padStart(2, '0')}`);
}
