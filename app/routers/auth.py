from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Body
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from datetime import datetime, timedelta
import random
import string
import os
import uuid
import redis.asyncio as redis
import logging

from app.database import get_db
from app.schemas import dtos
from app.models import tables
from app.core import security
from app.core.security import get_password_hash

# Configura o Logger
logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["Authentication"])

# --- CONFIGURAÇÃO DE EMAIL ---
conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM", "admin@idnofunny.com"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=False, # Resolve o problema de travamento no Docker
    TIMEOUT=30            # Dá mais tempo para conectar
)

# URL do Frontend (Ajuste se seu app rodar em outra porta, ex: 5173 ou 8100)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8100")

# --- FUNÇÕES AUXILIARES ---
def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

async def send_verification_email(email: EmailStr, code: str):
    logger.info(f"📨 [Background] Enviando código de ativação para: {email}")
    
    html = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px; color: #333;">
        <h2>Bem-vindo ao IDNOFunny!</h2>
        <p>Use o código abaixo para ativar sua conta:</p>
        <h1 style="color: #fff; background-color: #5b4ddb; padding: 10px 20px; display: inline-block; border-radius: 8px;">{code}</h1>
        <p>Este código expira em 10 minutos.</p>
    </div>
    """

    message = MessageSchema(
        subject="Ative sua conta IDNOFunny 🚀",
        recipients=[email],
        body=html,
        subtype=MessageType.html
    )

    try:
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info(f"✅ Email de ativação enviado para {email}")
    except Exception as e:
        logger.error(f"❌ Erro ao enviar email de ativação: {e}")

# --- NOVA FUNÇÃO: ENVIA O LINK DE RECUPERAÇÃO ---
async def send_recovery_email(email: EmailStr, token: str):
    logger.info(f"📨 [Background] Enviando link de recuperação para: {email}")
    
    reset_link = f"{FRONTEND_URL}/reset-password?token={token}"
    
    html = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px; color: #333;">
        <h2>Recuperação de Senha 🔐</h2>
        <p>Você solicitou a alteração da sua senha no IDNOFunny.</p>
        <p>Clique no botão abaixo para criar uma nova senha:</p>
        <a href="{reset_link}" style="background-color: #d63031; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">Redefinir Senha</a>
        <p style="margin-top: 20px; font-size: 12px; color: #777;">Se não foi você, apenas ignore este email.</p>
        <p style="font-size: 12px; color: #777;">Link válido por 30 minutos.</p>
    </div>
    """

    message = MessageSchema(
        subject="Recuperação de Senha - IDNOFunny",
        recipients=[email],
        body=html,
        subtype=MessageType.html
    )

    try:
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info(f"✅ Email de recuperação enviado para {email}")
    except Exception as e:
        logger.error(f"❌ Erro ao enviar email de recuperação: {e}")

# --- ROTAS ---

@router.post("/register", response_model=dtos.UserResponse)
async def register(
    user: dtos.UserCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    if db.query(tables.User).filter(tables.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username já existe")
    if db.query(tables.User).filter(tables.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    
    hashed_pwd = security.get_password_hash(user.password)
    new_user = tables.User(
        username=user.username, 
        email=user.email, 
        hashed_password=hashed_pwd,
        is_active=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    code = generate_code()
    redis_conn = redis.from_url(os.getenv("REDIS_URL", "redis://cache:6379"), encoding="utf-8", decode_responses=True)
    await redis_conn.setex(f"verify:{user.email}", 600, code)
    
    background_tasks.add_task(send_verification_email, user.email, code)
    
    logger.info(f"👤 Novo usuário registrado: {user.username}")
    return new_user

@router.post("/verify")
async def verify_email(
    verification: dtos.EmailVerification,
    db: Session = Depends(get_db)
):
    redis_conn = redis.from_url(os.getenv("REDIS_URL", "redis://cache:6379"), encoding="utf-8", decode_responses=True)
    stored_code = await redis_conn.get(f"verify:{verification.email}")
    
    if not stored_code or stored_code != verification.code:
        raise HTTPException(status_code=400, detail="Código inválido ou expirado")
    
    user = db.query(tables.User).filter(tables.User.email == verification.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    user.is_active = True
    db.commit()
    await redis_conn.delete(f"verify:{verification.email}")
    
    return {"message": "Conta ativada! Pode logar."}

@router.post("/token", response_model=dtos.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(tables.User).filter(tables.User.username == form_data.username).first()
    
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Email não verificado.")
    
    access_token = security.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# --- ROTAS DE RECUPERAÇÃO DE SENHA (ATUALIZADA) ---

@router.post("/password-recovery/{email}")
def request_password_recovery(
    email: str, 
    background_tasks: BackgroundTasks, # <--- Injetamos BackgroundTasks
    db: Session = Depends(get_db)
):
    user = db.query(tables.User).filter(tables.User.email == email).first()
    
    # Se usuário não existe, retornamos sucesso falso por segurança
    if not user:
        logger.info(f"Recuperação solicitada para email inexistente: {email}")
        return {"message": "Se o email existir, enviamos um link."}

    # Gera token
    token = str(uuid.uuid4())
    
    # Salva no banco
    user.reset_token = token
    user.reset_token_expires = datetime.utcnow() + timedelta(minutes=30)
    db.commit()

    # ENVIA O EMAIL EM BACKGROUND (DE VERDADE AGORA)
    background_tasks.add_task(send_recovery_email, user.email, token)

    return {"message": "Se o email existir, enviamos um link."}

@router.post("/reset-password")
def reset_password(
    token: str = Body(..., embed=True), 
    new_password: str = Body(..., embed=True), 
    db: Session = Depends(get_db)
):
    user = db.query(tables.User).filter(tables.User.reset_token == token).first()
    
    if not user:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")

    if user.reset_token_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token expirado")

    user.hashed_password = security.get_password_hash(new_password)
    
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()

    logger.info(f"🔐 Senha resetada: {user.username}")
    return {"message": "Senha alterada com sucesso! Faça login."}