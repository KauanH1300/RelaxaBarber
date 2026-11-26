import React from 'react';
import ReactDOM from 'react-dom/client';
import { RecuperarSenhaEquipe } from './pages/auth/RecuperarSenhaEquipe';
import { BrowserRouter, Routes, Route, Link, Navigate, useLocation } from 'react-router-dom';
import App from './pages/auth/Login';
import { ListaServicos } from './pages/servicos/ListaServicos';
import { FormServico } from './pages/servicos/FormServico';
import { Layout } from './components/layout';
import  Agenda from './pages/agendamentos/Agenda';
import { Perfil } from './pages/perfil/Perfil';
import { SomenteAdministrador } from './components/SomenteAdministrador';
import { ClientesUnidade } from './pages/unidade/ListasUnidade';
import { Comandas } from './pages/comandas/Comandas';
import { Estoque } from './pages/estoque/Estoque';
import { EditarProduto } from './pages/estoque/EditarProduto';
import { HorariosFilial } from './pages/horarios/HorariosFilial';
import { Funcionarios } from './pages/funcionarios/Funcionarios';
import './index.css';
import { AcessoCliente, InicioCliente } from './pages/portal/PortalCliente';
import { TrocaEmailCliente } from './pages/portal/TrocaEmailCliente';
import { InicioPublico } from './pages/publico/InicioPublico';
import { AgendamentoPublico } from './pages/publico/AgendamentoPublico';
import { MeusAgendamentos } from './pages/portal/MeusAgendamentos';
import { Repasses } from './pages/repasses/Repasses';
import { Gerencial } from './pages/gerencial/GerencialLazy';

function RedirecionarVitrine() {
  const { search } = useLocation();
  return <Navigate replace to={{ pathname: '/', search, hash: '#vitrine' }} />;
}

const indisponivel = <main><p>Funcionalidade ainda indisponível.</p><Link to="/login">Voltar ao login</Link></main>;

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<App />} />
        <Route path="/cliente/trocar-email" element={<TrocaEmailCliente />} />
        <Route path="/cliente/agendamentos" element={<MeusAgendamentos />} />
        {(['entrar', 'cadastro', 'recuperar', 'ativar', 'redefinir'] as const).map(modo => <Route key={modo} path={`/cliente/${modo}`} element={<AcessoCliente key={modo} modo={modo} />} />)}
        <Route path="/cliente" element={<InicioCliente />} />
        <Route path="/cliente/conta" element={<InicioCliente />} />
        <Route path="/cadastro" element={indisponivel} />
        <Route path="/recuperar-senha" element={<RecuperarSenhaEquipe />} />
        <Route path="/nova-senha" element={indisponivel} />
        
       <Route element={<Layout />}>
        <Route path="/clientes" element={<ClientesUnidade />} />
        <Route path="/funcionarios" element={<Funcionarios />} />
        <Route path="/comandas" element={<Comandas />} />
        <Route path="/repasses" element={<SomenteAdministrador mensagem="Sem permissão para acessar repasses." retorno="/agendamentos"><Repasses /></SomenteAdministrador>} />
        <Route path="/gerencial" element={<SomenteAdministrador mensagem="Sem permissão para acessar o Gerencial." retorno="/agendamentos"><React.Suspense fallback={<p role="status">Carregando Gerencial…</p>}><Gerencial /></React.Suspense></SomenteAdministrador>} />
        <Route path="/estoque" element={<Estoque />} />
        <Route path="/estoque/:id/editar" element={<EditarProduto />} />
        <Route path="/expediente" element={<HorariosFilial />} />
        <Route path="/perfil" element={<Perfil />} />
        <Route path="/agendamentos" element={<Agenda />} /> 
        <Route path="/servicos" element={<ListaServicos />} />
        <Route path="/servicos/novo" element={<SomenteAdministrador><FormServico /></SomenteAdministrador>} />
        <Route path="/servicos/:id/editar" element={<SomenteAdministrador><FormServico /></SomenteAdministrador>} />
      </Route>

<Route path="/" element={<InicioPublico />} />
<Route path="/agendar" element={<AgendamentoPublico />} />
<Route path="/vitrine" element={<RedirecionarVitrine />} />
<Route path="*" element={<main><p>Página não disponível.</p><Link to="/">Voltar ao início</Link></main>} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
