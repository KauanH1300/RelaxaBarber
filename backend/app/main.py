from fastapi import FastAPI

app = FastAPI(
    title="RelaxaBarber API",
    description="API de Gestão para a Barbearia RelaxaBarber",
    version="1.0.0",
)

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