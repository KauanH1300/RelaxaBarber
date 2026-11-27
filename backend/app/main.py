from app.core.logging import install_safe_logging

install_safe_logging()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db.database import engine
from app.frontend import Frontend
from app.api.routes import filiais, auth, usuarios, servico, agendamentos, clientes, comandas, comandas_avulsas, financeiro
from app.api.routes import itens_comanda, beneficios, cancelamento_comanda
from app.api.routes import portal_clientes
from app.api.routes import reservas_publicas
from app.api.routes import minha_agenda, estoque, comissoes, repasses, gerencial, bloqueios_agenda, vitrine
from app.services.vitrine import ciclo_storage
import os
from fastapi.middleware.cors import CORSMiddleware
from app.api.exception_handlers import registrar_erros_persistencia
from app.core.ambiente import origens_permitidas, producao
from app.core.http_producao import HTTPProducao

PUBLICADA = producao()
ORIGENS = origens_permitidas()


class Aplicacao(FastAPI):
    def build_middleware_stack(self):
        stack = CORSMiddleware(
            super().build_middleware_stack(), allow_origins=ORIGENS,
            allow_methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
            allow_headers=['Content-Type', 'X-Equipe-CSRF', 'Idempotency-Key', 'If-Match'],
            expose_headers=['ETag'], allow_credentials=True,
        )
        return HTTPProducao(stack, ORIGENS) if PUBLICADA else stack


app = Aplicacao(
    title="RelaxaBarber API",
    description="API de Gestão para a Barbearia RelaxaBarber",
    version="1.0.0",
    lifespan=ciclo_storage,
    debug=False,
    docs_url=None if PUBLICADA else '/docs',
    redoc_url=None if PUBLICADA else '/redoc',
    openapi_url=None if PUBLICADA else '/openapi.json',
)
registrar_erros_persistencia(app)

if PUBLICADA:
    @app.exception_handler(Exception)
    async def erro_inesperado(request: Request, exc: Exception):
        return JSONResponse({'detail': 'Falha interna no processamento da solicitação.'}, status_code=500)

# tratamento global dos erros de validaçao dos schemas pydantic e converte as mensagens padrao do fastAPI/pydantic para mensagens mais claras e especificas para o usuario da api
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    erros = []
    fluxo_servicos = request.url.path == "/servicos" or request.url.path.startswith("/servicos/")
    nomes_campos_servico = {
        "nome": "Nome", "preco": "Preço", "tempo_estimado": "Tempo estimado",
        "comissao_padrao": "Comissão padrão", "ativo": "Status do serviço",
        "servico_id": "Identificador do serviço",
    }
    
    # percorre todos os erros encontrados na requisiçao
    for erro in exc.errors():
        campo = erro["loc"][-1]
        tipo = erro["type"]
        msg = erro["msg"]
        if PUBLICADA and (campo in {'password', 'username', 'senha', 'senha_atual', 'senha_atual_admin',
                                    'codigo', 'token', 'email', 'email_novo'}
                          or tipo in {'extra_forbidden', 'json_invalid'}):
            erros.append('Dados em formato inválido. Confira os valores informados.')
            continue
        if fluxo_servicos:
            campo = nomes_campos_servico.get(campo, "Dados do serviço")
        
        # erros personalizados gerados pelos validators dos schemas 
        if tipo == "value_error":
            # remove o prefixo padrao que o pydantic adiciona
            mensagem = msg.replace("Value error, ", "")
            erros.append(mensagem)

        # campo obrigatorio nao informado
        elif tipo == "missing":
            erros.append(f"O campo '{campo}' é obrigatório.")

        # campo numerico que precisa ser maior que zero
        elif tipo == "greater_than":
            erros.append(f"O campo '{campo}' deve ser maior que zero.")

        # campo de texto vazio
        elif tipo == "string_too_short":
            erros.append(f"O campo '{campo}' não pode estar vazio.")

        # tratamento para outros tipos de erro de validaçao
        else:
            if fluxo_servicos:
                erros.append(f"O campo '{campo}' está em formato inválido. Confira o valor informado.")
            else:
                erros.append(f"Erro no campo '{campo}': {msg}")
            
# retorna os erros em um formato padronizado para a api
    return JSONResponse(
        status_code=422,
        content={"detail": erros}
    )

# registro das rotas da aplicaçao
app.include_router(comissoes.router)
app.include_router(repasses.router)
app.include_router(gerencial.router)
app.include_router(estoque.router)
app.include_router(vitrine.router)
app.include_router(filiais.router)
app.include_router(portal_clientes.router)
app.include_router(reservas_publicas.router)
app.include_router(minha_agenda.router)
app.include_router(itens_comanda.router)
app.include_router(beneficios.router)
app.include_router(cancelamento_comanda.router)
app.include_router(auth.router)
app.include_router(servico.router)
app.include_router(usuarios.router)
app.include_router(bloqueios_agenda.router)
app.include_router(agendamentos.router)
app.include_router(clientes.router)
app.include_router(comandas_avulsas.router)
app.include_router(comandas.router)
app.include_router(financeiro.router)

# rota principal da api
@app.get("/")
def read_root():
    return {
        "projeto": "RelaxaBarber",
        "status": "online",
        **({} if PUBLICADA else {"docs": "/docs"}),
        "health": "/health",
    }
    
# rota usada para verificar se a api esta funcionando
@app.get("/health")
@app.head("/health", include_in_schema=False)
def health_check():
    return {"status": "ok", "sistema": "RelaxaBarber"}


@app.get("/ready", responses={503: {"description": "PostgreSQL indisponível"}})
@app.head("/ready", include_in_schema=False)
def readiness_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "indisponível"}, status_code=503, headers={"Cache-Control": "no-store"})
    return JSONResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})


if diretorio := os.getenv('FRONTEND_DIST'):
    app.add_middleware(Frontend, diretorio=diretorio)
