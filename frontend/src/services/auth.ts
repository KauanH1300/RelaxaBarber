import api from './api';

export async function login(email: string, senha: string) {
  const dados = new URLSearchParams();
  dados.append('username', email);
  dados.append('password', senha);

  const { data } = await api.post('/auth/login', dados, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });

  localStorage.setItem('token', data.access_token);
  return data;
}

export async function getMe() {
  const { data } = await api.get('/auth/me');
  return data;
}

export function logout() {
  localStorage.removeItem('token');
}