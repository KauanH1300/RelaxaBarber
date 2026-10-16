import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom';
import App from './pages/auth/Login';
import { ListaServicos } from './pages/servicos/ListaServicos';
import { FormServico } from './pages/servicos/FormServico';
import { Layout } from './components/layout';
import  Agenda from './pages/agendamentos/Agenda';
import { Perfil } from './pages/perfil/Perfil';
import { SomenteAdministrador } from './components/SomenteAdministrador';
import { ClientesUnidade, ComandasUnidade } from './pages/unidade/ListasUnidade';
import './index.css';

const indisponivel = <main><p>Funcionalidade ainda indisponível.</p><Link to="/login">Voltar ao login</Link></main>;

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<App />} />
        <Route path="/cadastro" element={indisponivel} />
        <Route path="/recuperar-senha" element={indisponivel} />
        <Route path="/nova-senha" element={indisponivel} />
        
       <Route element={<Layout />}>
        <Route path="/clientes" element={<ClientesUnidade />} />
        <Route path="/comandas" element={<ComandasUnidade />} />
        <Route path="/perfil" element={<Perfil />} />
        <Route path="/agendamentos" element={<Agenda />} /> 
        <Route path="/servicos" element={<ListaServicos />} />
        <Route path="/servicos/novo" element={<SomenteAdministrador><FormServico /></SomenteAdministrador>} />
        <Route path="/servicos/:id/editar" element={<SomenteAdministrador><FormServico /></SomenteAdministrador>} />
      </Route>

<Route path="/" element={<Navigate to="/agendamentos" replace />} />
<Route path="*" element={<main><p>Página não disponível.</p><Link to="/agendamentos">Voltar à agenda</Link></main>} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);