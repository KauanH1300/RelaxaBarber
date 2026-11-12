/** Ícones vetoriais locais para manter os controles legíveis sem fontes externas. */
const caminhos: Record<string, string> = {
  refresh: 'M20 7v5h-5 M20 12a8 8 0 1 0-2.3 5.7 M20 7l-2.3-2.3',
  receipt_long: 'M5 3l2 1 2-1 3 1 3-1 2 1 2-1v18l-2-1-2 1-3-1-3 1-2-1-2 1V3 M8 8h8 M8 12h8 M8 16h5',
  payments: 'M3 6h18v12H3z M7 6v3H3 M17 18v-3h4 M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  credit_card_off: 'M3 3l18 18 M4 7V5h16v14h-2 M4 11h4 M4 15v4h10 M12 9h8',
  task_alt: 'M20 11v1a8 8 0 1 1-4.5-7.2 M8 11l4 4 9-11',
  search: 'M10.5 3a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15 M16 16l5 5',
  grid_view: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  view_list: 'M3 4h4v4H3z M11 6h10 M3 10h4v4H3z M11 12h10 M3 16h4v4H3z M11 18h10',
  person: 'M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M4 21v-2a8 6 0 0 1 16 0v2',
  schedule: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 M12 6v6l4 2',
  arrow_forward: 'M4 12h16 M14 6l6 6-6 6',
  chevron_left: 'M15 5l-7 7 7 7',
  chevron_right: 'M9 5l7 7-7 7',
  info: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 M12 11v6 M12 7h.01',
  cloud_off: 'M3 3l18 18 M6 17H5a4 4 0 0 1-1-7.9 M8 6a6 6 0 0 1 10 3 4 4 0 0 1 3 7 M10 17h5',
  close: 'M6 6l12 12 M18 6L6 18',
  calendar_today: 'M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16',
  group: 'M9 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6 M3 20v-3a6 5 0 0 1 12 0v3 M16 4a3 3 0 0 1 0 6 M18 13a5 4 0 0 1 3 4v3',
  content_cut: 'M5 14a3 3 0 1 0 0 6 3 3 0 0 0 0-6 M5 4a3 3 0 1 0 0 6 3 3 0 0 0 0-6 M8 8l13 12 M8 16L21 4',
  logout: 'M9 4H4v16h5 M9 12h12 M16 7l5 5-5 5',
};
export function Icone({ nome }: { nome: string }) {
  return <svg className="icone" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={caminhos[nome] ?? caminhos.info} /></svg>;
}
