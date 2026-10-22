from app.core.logging import install_safe_logging

install_safe_logging()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.routes import filiais, auth, usuarios, servico, agendamentos, clientes, comandas
import json
import os
from fastapi.middleware.cors import CORSMiddleware
from app.api.exception_handlers import registrar_erros_persistencia

app = FastAPI(
    title="RelaxaBarber API",
    description="API de Gestão para a Barbearia RelaxaBarber",
    version="1.0.0",
)
registrar_erros_persistencia(app)

origens = json.loads(
    os.getenv(
        "BACKEND_CORS_ORIGINS",
        '["http://localhost:5173", "http://127.0.0.1:5173"]',
    )
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origens,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(filiais.router)
app.include_router(auth.router)
app.include_router(servico.router)
app.include_router(usuarios.router)
app.include_router(agendamentos.router)
app.include_router(clientes.router)
app.include_router(comandas.router)

# rota principal da api
@app.get("/")
def read_root():
    return {
        "projeto": "RelaxaBarber",
        "status": "online",
        "docs": "/docs",
        "health": "/health",
    }
    
# rota usada para verificar se a api esta funcionando
@app.get("/health")
def health_check():
    return {"status": "ok", "sistema": "RelaxaBarber"}
