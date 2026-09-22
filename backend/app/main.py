from fastapi import FastAPI

from app.api.routes import auth,usuarios,servico

app = FastAPI(
    title="RelaxaBarber API",
    description="API de Gestão para a Barbearia RelaxaBarber",
    version="1.0.0",
)

app.include_router(auth.router)
app.include_router(servico.router)
app.include_router(usuarios.router)

@app.get("/")
def read_root():
  return {
      "projeto": "RelaxaBarber",
      "status": "online",
      "docs": "/docs",
      "health": "/health",
  }
  
@app.get("/health")
def health_check():
  return {"status": "ok", "sistema": "RelaxaBarber"}