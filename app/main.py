from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi_limiter import FastAPILimiter
import redis.asyncio as redis
import os
import socket
from dotenv import load_dotenv
from sqlalchemy.orm import Session 
from app.database import engine, SessionLocal 
from app.models import tables 
from app.routers import auth, memes, users

load_dotenv()

# CRIA AS TABELAS NO BANCO AO INICIAR (Para simplificar sem Alembic por enquanto)
tables.Base.metadata.create_all(bind=engine)

app = FastAPI(title="IDNOFunny Pro API", version="2.0.0")

# --- CORS ---
origins = ["*"] # Em produção, especifique os domínios
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- STATIC FILES CORS MIDDLEWARE ---
@app.middleware("http")
async def add_cors_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        # Permite acesso irrestrito a arquivos estáticos (necessário para download/canvas)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        # Remove header de credenciais se existir, pois conflita com Origin: *
        if "Access-Control-Allow-Credentials" in response.headers:
            del response.headers["Access-Control-Allow-Credentials"]
    return response

# --- STATIC FILES ---
os.makedirs("uploads", exist_ok=True)
# Apenas uma montagem para uploads (que já contém avatars como subpasta)
app.mount("/static", StaticFiles(directory="uploads"), name="static")

# --- REDIS ---
@app.on_event("startup")
async def startup():
    # 1. Redis
    redis_url = os.getenv("REDIS_URL", "redis://cache:6379")
    redis_connection = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    await FastAPILimiter.init(redis_connection)
    
    # 2. Criar Categorias Padrão
    db = SessionLocal()
    try:
        default_categories = ["Humor", "Tecnologia", "Política", "Games", "Anime", "Aleatório"]
        for cat_name in default_categories:
            exists = db.query(tables.Category).filter(tables.Category.name == cat_name).first()
            if not exists:
                db.add(tables.Category(name=cat_name))
        db.commit()
    finally:
        db.close()


# --- ROTEADORES (AQUI A MÁGICA ACONTECE) ---
# Inclui as rotas de autenticação (ex: /register vira /auth/register se usarmos prefix)
app.include_router(auth.router)
app.include_router(memes.router)
app.include_router(users.router)

@app.get("/test-network")
def test_network():
    try:
        # Tenta criar uma conexão TCP simples
        socket.create_connection(("smtp.gmail.com", 587), timeout=5)
        return {"status": "success", "message": "Conexão TCP com Gmail OK!"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/")
def root():
    return {"system": "IDNOFunny Pro", "status": "Running"}