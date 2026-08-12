from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importe seus routers aqui:
# from app.views.user_routes import router as user_router

app = FastAPI(
    title="Vintex API",
    description="Backend da aplicação Vintex",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registre seus routers aqui:
# app.include_router(user_router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "ok"}
