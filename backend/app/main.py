from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.routes import auth, usuarios, servico

app = FastAPI(
    title="RelaxaBarber API",
    description="API de Gestão para a Barbearia RelaxaBarber",
    version="1.0.0",
)

# tratamento global dos erros de validaçao dos schemas pydantic e converte as mensagens padrao do fastAPI/pydantic para mensagens mais claras e especificas para o usuario da api
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    erros = []
    
    # percorre todos os erros encontrados na requisiçao
    for erro in exc.errors():
        campo = erro["loc"][-1]
        tipo = erro["type"]
        msg = erro["msg"]
        
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
            erros.append(f"Erro no campo '{campo}': {msg}")
            
# retorna os erros em um formato padronizado para a api
    return JSONResponse(
        status_code=422,
        content={"detail": erros}
    )

# registro das rotas da aplicaçao
app.include_router(auth.router)
app.include_router(servico.router)
app.include_router(usuarios.router)

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
