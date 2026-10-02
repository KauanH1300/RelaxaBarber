import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import App from './pages/auth/Login';
import Cadastro from './pages/auth/Cadastro';
import RecuperarSenha from './pages/auth/RecuperarSenha';
import NovaSenha from './pages/auth/NovaSenha';
import { ListaServicos } from './pages/servicos/ListaServicos';
import { FormServico } from './pages/servicos/FormServico';
import { Agenda } from './pages/navbar/Agenda'; 
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        {/* linha abaixo é usada para testes de telas rapido e facil. está predefinido como Agenda para testar as novas funcionalidades da agenda. */} 
        {/*  <Route path="/" element={<Agenda />} /> */} 

        <Route path="/login" element={<App />} />
        <Route path="/cadastro" element={<Cadastro />} />
        <Route path="/recuperar-senha" element={<RecuperarSenha />} />
        <Route path="/nova-senha" element={<NovaSenha />} />
        <Route path="/agenda" element={<Agenda />} />
        <Route path="/servicos" element={<ListaServicos />} />
        <Route path="/servicos/novo" element={<FormServico />} />
        <Route path="/servicos/:id/editar" element={<FormServico />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);