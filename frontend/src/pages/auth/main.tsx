import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import App from './Login';
import Cadastro from './Cadastro';
import RecuperarSenha from './RecuperarSenha';
import NovaSenha from './NovaSenha';
import { ListaServicos } from './pages/servicos/ListaServicos';
import { FormServico } from './pages/servicos/FormServico';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<App />} />
        <Route path="/cadastro" element={<Cadastro />} />
        <Route path="/recuperar-senha" element={<RecuperarSenha />} />
        <Route path="/nova-senha" element={<NovaSenha />} />
                <Route path="/servicos" element={<ListaServicos />} />
        <Route path="/servicos/novo" element={<FormServico />} />
        <Route path="/servicos/:id/editar" element={<FormServico />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);