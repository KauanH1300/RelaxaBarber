import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import App from './pages/auth/Login';
import Cadastro from './pages/auth/Cadastro';
import RecuperarSenha from './pages/auth/RecuperarSenha';
import NovaSenha from './pages/auth/NovaSenha';
import { ListaServicos } from './pages/servicos/ListaServicos';
import { FormServico } from './pages/servicos/FormServico';
import { Layout } from './components/layout';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<App />} />
        <Route path="/cadastro" element={<Cadastro />} />
        <Route path="/recuperar-senha" element={<RecuperarSenha />} />
        <Route path="/nova-senha" element={<NovaSenha />} />
        
       <Route element={<Layout />}>
  <Route path="/servicos" element={<ListaServicos />} />
  <Route path="/servicos/novo" element={<FormServico />} />
  <Route path="/servicos/:id/editar" element={<FormServico />} />
</Route>

<Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);