from typing import List
from sqlalchemy import func
import os
import shutil
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import dtos
from app.models import tables
from app.core.deps import get_current_user
from app.core.security import verify_password

# Configuração da pasta de uploads
UPLOAD_DIR = "uploads/avatars"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(tags=["Users & Social"])

# --- 1. VER MEU PRÓPRIO PERFIL ---
@router.get("/users/me", response_model=dtos.UserProfile)
def read_users_me(
    db: Session = Depends(get_db), 
    current_user: tables.User = Depends(get_current_user)
):
    current_user.memes_count = len(current_user.memes)
    current_user.followers_count = len(current_user.followers)
    current_user.following_count = len(current_user.following)

    total_likes = db.query(func.count(tables.MemeLike.user_id))\
        .join(tables.Meme)\
        .filter(tables.Meme.owner_id == current_user.id)\
        .scalar()
    
    current_user.total_likes = total_likes or 0
    current_user.is_following = False 
    
    return current_user

# --- 2. UPLOAD DE AVATAR (CORREÇÃO DE UUID) ---
@router.post("/users/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: tables.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Apenas imagens são permitidas.")

    file_extension = file.filename.split(".")[-1]
    
    # --- CORREÇÃO AQUI ---
    # Geramos o nome UMA ÚNICA VEZ e salvamos na variável 'unique_name'
    unique_name = f"avatar_{current_user.id}_{uuid.uuid4()}.{file_extension}"
    
    # Usamos a MESMA variável para o caminho físico
    file_path = f"{UPLOAD_DIR}/{unique_name}"
    
    # Usamos a MESMA variável para o link do banco
    image_url = f"/static/avatars/{unique_name}"
    
    # Salva no disco
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Salva no banco
    current_user.avatar_url = image_url
    db.commit()
    db.refresh(current_user)
    
    # O print vai aparecer no terminal para você confirmar que os nomes são iguais
    print(f"✅ ARQUIVO SALVO: {file_path}")
    print(f"✅ URL NO BANCO:  {image_url}")
    
    return {"avatar_url": image_url, "message": "Foto atualizada!"}

# --- 3. VER PERFIL DE OUTRA PESSOA ---
@router.get("/users/{username}", response_model=dtos.UserProfile)
def read_user(
    username: str, 
    db: Session = Depends(get_db),
    current_user: tables.User = Depends(get_current_user)
):
    user = db.query(tables.User).filter(tables.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    user.memes_count = len(user.memes)
    user.followers_count = len(user.followers)
    user.following_count = len(user.following)
    
    total_likes = db.query(func.count(tables.MemeLike.user_id))\
        .join(tables.Meme)\
        .filter(tables.Meme.owner_id == user.id)\
        .scalar()
    
    user.total_likes = total_likes or 0
    user.is_following = current_user in user.followers
    
    return user

# --- 4. SEGUIR / DEIXAR DE SEGUIR ---
@router.post("/users/{username}/follow")
def follow_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: tables.User = Depends(get_current_user)
):
    target_user = db.query(tables.User).filter(tables.User.username == username).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode seguir a si mesmo")

    if current_user in target_user.followers:
        target_user.followers.remove(current_user)
        message = f"Deixou de seguir {username}"
        is_following = False
    else:
        target_user.followers.append(current_user)
        message = f"Seguindo {username}"
        is_following = True
        
    db.commit()
    return {"message": message, "is_following": is_following}

# --- 5. HISTÓRICO: MEMES POSTADOS ---
@router.get("/users/{username}/memes", response_model=List[dtos.MemeResponse])
def read_user_memes(
    username: str, 
    db: Session = Depends(get_db)
):
    user = db.query(tables.User).filter(tables.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    return db.query(tables.Meme).filter(tables.Meme.owner_id == user.id).order_by(tables.Meme.created_at.desc()).all()

# --- 6. HISTÓRICO: MEMES CURTIDOS ---
@router.get("/users/{username}/likes", response_model=List[dtos.MemeResponse])
def read_user_likes(
    username: str, 
    db: Session = Depends(get_db),
    current_user: tables.User = Depends(get_current_user)
):
    user = db.query(tables.User).filter(tables.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    liked_memes = db.query(tables.Meme).join(tables.MemeLike).filter(tables.MemeLike.user_id == user.id).all()
    
    my_likes = {like.meme_id for like in db.query(tables.MemeLike).filter(tables.MemeLike.user_id == current_user.id).all()}
    
    for meme in liked_memes:
        meme.is_liked_by_me = meme.id in my_likes
        
    return liked_memes

# --- 7. HISTÓRICO: COMENTÁRIOS ---
@router.get("/users/{username}/comments", response_model=List[dtos.CommentResponse])
def read_user_comments(
    username: str,
    db: Session = Depends(get_db)
):
    user = db.query(tables.User).filter(tables.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    return db.query(tables.Comment).filter(tables.Comment.owner_id == user.id).order_by(tables.Comment.created_at.desc()).all()

# --- 8. DELETAR CONTA (Soft Delete / Anonimização) ---
@router.delete("/users/me")
def delete_user_me(
    db: Session = Depends(get_db), 
    current_user: tables.User = Depends(get_current_user)
):
    # Gera identificador único para não conflitar no banco
    random_id = str(uuid.uuid4())[:8]
    
    # Anonimiza (Soft Delete)
    current_user.username = f"Usuário Deletado {random_id}"
    current_user.email = f"deleted_{random_id}@inactive.com"
    current_user.avatar_url = None # Remove a foto
    current_user.is_active = False
    current_user.hashed_password = "DELETED" # Bloqueia login
    
    # OBS: NÃO CHAME db.delete(current_user)
    db.add(current_user) # Garante o Update
    db.commit()
    
    return {"message": "Conta desativada com sucesso. Suas interações foram mantidas anonimamente."}