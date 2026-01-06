from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func 
from typing import List, Optional
from fastapi_limiter.depends import RateLimiter
import os
import uuid
import shutil
from PIL import Image, ImageOps
from datetime import datetime, timedelta

# Import da biblioteca de filtro
from better_profanity import profanity 

from app.database import get_db
from app.schemas import dtos
from app.models import tables
from app.core.deps import get_current_user

router = APIRouter(tags=["Memes & Discovery"])

# Garante que as pastas existem
UPLOAD_DIR = "uploads"
VIDEO_DIR = "uploads/videos"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# ... (profanity config remains same) ...
try:
    profanity.load_censor_words()
    custom_bad_words = [
        "trouxa", "idiota", "imbecil", "burro", "lixo", "merda", 
        "bosta", "droga", "feio", "horrivel", "odiei", "puta", "caralho"
    ]
    profanity.add_censor_words(custom_bad_words)
except Exception as e:
    print(f"Erro ao carregar profanity: {e}")

# ... (rate limiter remains same) ...
async def user_id_identifier(request: Request):
    auth = request.headers.get("Authorization")
    if auth: return auth
    return request.client.host or "127.0.0.1"

# --- FUNÇÕES ÚTEIS ---
def get_media_type(file: UploadFile) -> str:
    content_type = file.content_type
    if content_type.startswith("image/"):
        return "image"
    elif content_type.startswith("video/"):
        return "video"
    return "unknown"

def validate_file(file: UploadFile, media_type: str) -> bool:
    try:
        header = file.file.read(1024)
        file.file.seek(0)
        
        if media_type == "image":
            # JPEG (FF D8 FF) or PNG (89 50 4E 47)
            return header.startswith(b'\xff\xd8\xff') or header.startswith(b'\x89PNG\r\n\x1a\n')
        
        elif media_type == "video":
            # MP4/MOV (Check for 'ftyp' signature usually at byte 4)
            # WEBM (1A 45 DF A3)
            if header.startswith(b'\x1a\x45\xdf\xa3'): return True # WEBM
            
            # Simple check for ftyp in first 12 bytes for MP4/MOV
            # Common signatures: 00 00 00 18 66 74 79 70 (ftyp)
            if b'ftyp' in header[:20]: return True
            
            return False
            
    except: return False
    return False

def process_upload(file: UploadFile, media_type: str) -> Optional[str]:
    try:
        filename = f"{uuid.uuid4()}"
        
        if media_type == "image":
            image = Image.open(file.file)
            image = ImageOps.exif_transpose(image)
            if image.mode in ("RGBA", "P"): image = image.convert("RGB")
            
            filepath = f"{UPLOAD_DIR}/{filename}.jpg"
            image.save(filepath, format="JPEG", quality=85, optimize=True)
            return f"/static/{filename}.jpg"
            
        elif media_type == "video":
            # Verificar tamanho (aprox 50MB)
            file.file.seek(0, 2)
            size = file.file.tell()
            file.file.seek(0)
            
            if size > 50 * 1024 * 1024: # 50MB
                raise Exception("Arquivo muito grande (Max 50MB)")
            
            extension = file.filename.split('.')[-1].lower()
            if extension not in ['mp4', 'mov', 'webm']: extension = 'mp4'
            
            filepath = f"{VIDEO_DIR}/{filename}.{extension}"
            
            with open(filepath, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
                
            return f"/static/videos/{filename}.{extension}"
            
    except Exception as e:
        print(f"Erro upload: {e}")
        return None

# ... (get_categories, search_memes remain same) ...
# --- ROTAS DE DESCOBERTA ---
@router.get("/categories", response_model=List[dtos.CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    return db.query(tables.Category).all()

@router.get("/memes/search", response_model=List[dtos.MemeResponse])
def search_memes(q: Optional[str] = None, category_id: Optional[int] = None, hashtag: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(tables.Meme)
    if category_id: query = query.filter(tables.Meme.category_id == category_id)
    if q: query = query.filter(tables.Meme.title.ilike(f"%{q}%"))
    if hashtag: query = query.join(tables.Meme.hashtags).filter(tables.Hashtag.name == hashtag)
    return query.order_by(tables.Meme.created_at.desc()).all()

# ... (get_feed remains same) ...
# --- ROTAS DE MEMES (FEED) ---
@router.get("/memes", response_model=List[dtos.MemeResponse])
def get_feed(
    skip: int = 0, 
    limit: int = 100, 
    sort: str = "new",
    db: Session = Depends(get_db), 
    current_user: Optional[tables.User] = Depends(get_current_user)
):
    query = db.query(tables.Meme)

    if sort == "top":
        # ORDENAR POR MAIS CURTIDOS (usando subquery para evitar GroupingError)
        likes_subquery = db.query(
            tables.MemeLike.meme_id,
            func.count(tables.MemeLike.user_id).label("like_count")
        ).group_by(tables.MemeLike.meme_id).subquery()

        query = query.outerjoin(likes_subquery, tables.Meme.id == likes_subquery.c.meme_id)\
            .order_by(likes_subquery.c.like_count.desc().nullslast())
    else:
        # PADRÃO: ORDENAR POR DATA (Mais recentes)
        query = query.order_by(tables.Meme.created_at.desc())

    memes = query.offset(skip).limit(limit).all()
    
    if current_user:
        # Lógica segura para evitar IndexError
        raw_likes = db.query(tables.MemeLike.meme_id).filter(tables.MemeLike.user_id == current_user.id).all()
        liked_ids = {row[0] for row in raw_likes}
        
        following_ids = {u.id for u in current_user.following}

        for meme in memes: 
            meme.is_liked_by_me = meme.id in liked_ids
            # Definindo atributo dinamicamente (garanta que removeu a @property do tables.py)
            meme.owner_is_following = meme.owner_id in following_ids
            
    return memes

# ... (get_single_meme remains same) ...
@router.get("/memes/{meme_id}", response_model=dtos.MemeResponse)
def get_single_meme(meme_id: int, db: Session = Depends(get_db), current_user: Optional[tables.User] = Depends(get_current_user)):
    meme = db.query(tables.Meme).filter(tables.Meme.id == meme_id).first()
    if not meme: raise HTTPException(status_code=404, detail="Meme não encontrado")
    
    if current_user:
        is_liked = db.query(tables.MemeLike).filter(tables.MemeLike.user_id == current_user.id, tables.MemeLike.meme_id == meme_id).first()
        meme.is_liked_by_me = bool(is_liked)
        
        if current_user.id != meme.owner_id:
            meme.owner_is_following = meme.owner in current_user.following
        
        # Lógica segura para likes em comentários
        raw_comment_likes = db.query(tables.CommentLike.comment_id)\
            .filter(tables.CommentLike.user_id == current_user.id)\
            .join(tables.Comment).filter(tables.Comment.meme_id == meme_id).all()
        
        user_comment_likes = {row[0] for row in raw_comment_likes}
        
        for comment in meme.comments:
            comment.is_liked_by_me = comment.id in user_comment_likes
            
    return meme

# --- UPDATE CREATE_MEME ---
@router.post("/memes", response_model=dtos.MemeResponse, dependencies=[Depends(RateLimiter(times=1, seconds=60, identifier=user_id_identifier))])
def create_meme(title: str = Form(...), category_id: int = Form(...), tags: str = Form(""), file: UploadFile = File(...), db: Session = Depends(get_db), current_user: tables.User = Depends(get_current_user)):
    
    media_type = get_media_type(file)
    if media_type == "unknown":
         raise HTTPException(status_code=400, detail="Formato de arquivo não suportado (Use Imagem ou Vídeo)")

    if not validate_file(file, media_type): 
        raise HTTPException(status_code=400, detail=f"Arquivo inválido ou corrompido para o tipo {media_type}")
    
    url = process_upload(file, media_type)
    if not url: 
        raise HTTPException(status_code=500, detail="Erro ao processar upload (Verifique tamanho ou formato)")

    new_meme = tables.Meme(
        title=title, 
        image_url=url, 
        media_type=media_type,
        owner_id=current_user.id, 
        category_id=category_id
    )
    db.add(new_meme); db.commit(); db.refresh(new_meme)
    
    if tags:
        tag_list = [t.strip().lower().replace("#", "") for t in tags.split(",") if t.strip()]
        for tag_name in tag_list:
            hashtag_obj = db.query(tables.Hashtag).filter(tables.Hashtag.name == tag_name).first()
            if not hashtag_obj:
                hashtag_obj = tables.Hashtag(name=tag_name); db.add(hashtag_obj); db.commit()
            new_meme.hashtags.append(hashtag_obj)
        db.commit(); db.refresh(new_meme)
    return new_meme

@router.post("/memes/{meme_id}/like", response_model=dtos.LikeResponse)
def like_meme(meme_id: int, db: Session = Depends(get_db), current_user: tables.User = Depends(get_current_user)):
    meme = db.query(tables.Meme).filter(tables.Meme.id == meme_id).first()
    if not meme: raise HTTPException(status_code=404, detail="Meme não encontrado")
    
    existing_like = db.query(tables.MemeLike).filter(tables.MemeLike.user_id == current_user.id, tables.MemeLike.meme_id == meme_id).first()
    if existing_like:
        db.delete(existing_like); is_liked = False
    else:
        db.add(tables.MemeLike(user_id=current_user.id, meme_id=meme_id)); is_liked = True
        
    db.commit(); db.refresh(meme)
    return {"liked": is_liked, "total_likes": len(meme.likes)}

# --- COMENTÁRIOS COM ANTI-SPAM ---
@router.post("/memes/{meme_id}/comments", response_model=dtos.CommentResponse, dependencies=[Depends(RateLimiter(times=1, seconds=1, identifier=user_id_identifier))])
def create_comment(
    meme_id: int, 
    comment: dtos.CommentCreate, 
    db: Session = Depends(get_db), 
    current_user: tables.User = Depends(get_current_user)
):
    # 1. Verifica se o Meme existe
    meme = db.query(tables.Meme).filter(tables.Meme.id == meme_id).first()
    if not meme: 
        raise HTTPException(status_code=404, detail="Meme não encontrado")
    
    # 2. VERIFICAÇÃO DE TOXICIDADE (Palavrões)
    if profanity.contains_profanity(comment.text):
        raise HTTPException(
            status_code=400, 
            detail="Seu comentário contém linguagem inadequada. Vamos manter o chat saudável! 🙏"
        )

    # 3. VERIFICAÇÃO DE SPAM (Repetição de conteúdo)
    # Busca o último comentário desse usuário neste mesmo meme
    last_comment = db.query(tables.Comment)\
        .filter(tables.Comment.owner_id == current_user.id)\
        .filter(tables.Comment.meme_id == meme_id)\
        .order_by(desc(tables.Comment.created_at))\
        .first()

    if last_comment:
        # Verifica se o texto é idêntico
        if last_comment.text.strip().lower() == comment.text.strip().lower():
             raise HTTPException(
                status_code=400, 
                detail="Você já enviou essa mensagem. Evite spam! 🚫"
            )
        
        # Segurança extra: bloqueia flood muito rápido (menos de 2s)
        time_diff = datetime.utcnow() - last_comment.created_at
        if time_diff.total_seconds() < 1:
             raise HTTPException(status_code=429, detail="Vá com calma, cowboy! 🤠")

    # 4. Verifica comentário pai (se for resposta)
    if comment.parent_id:
        parent = db.query(tables.Comment).filter(tables.Comment.id == comment.parent_id).first()
        if not parent: 
            raise HTTPException(status_code=404, detail="Comentário pai não encontrado")

    # 5. Salva o comentário
    new_comment = tables.Comment(
        text=comment.text, 
        owner_id=current_user.id, 
        meme_id=meme_id, 
        parent_id=comment.parent_id
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    
    return new_comment

# --- NOVA ROTA: DENUNCIAR MEME ---
@router.post("/memes/{meme_id}/report", status_code=201)
def report_meme(
    meme_id: int, 
    report_data: dtos.ReportCreate,
    db: Session = Depends(get_db),
    current_user: tables.User = Depends(get_current_user)
):
    meme = db.query(tables.Meme).filter(tables.Meme.id == meme_id).first()
    if not meme: raise HTTPException(status_code=404, detail="Meme não encontrado")

    new_report = tables.Report(
        meme_id=meme_id,
        reporter_id=current_user.id,
        reason=report_data.reason
    )
    db.add(new_report)
    db.commit()
    return {"message": "Denúncia recebida. Obrigado por manter a comunidade segura."}

# --- NOVA ROTA: COMENTÁRIOS PAGINADOS (Para o 'Arrastar pra cima') ---
@router.get("/memes/{meme_id}/comments/list", response_model=List[dtos.CommentResponse])
def get_meme_comments(
    meme_id: int,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: Optional[tables.User] = Depends(get_current_user)
):
    # Essa rota é leve, só traz comentários, perfeita para o Modal
    comments = db.query(tables.Comment)\
        .filter(tables.Comment.meme_id == meme_id)\
        .order_by(tables.Comment.created_at.desc())\
        .offset(skip).limit(limit).all()
        
    if current_user:
        # Lógica segura para likes em comentários (Otimizada)
        comment_ids = [c.id for c in comments]
        if comment_ids:
            raw_comment_likes = db.query(tables.CommentLike.comment_id)\
                .filter(tables.CommentLike.user_id == current_user.id)\
                .filter(tables.CommentLike.comment_id.in_(comment_ids))\
                .all()
            
            user_comment_likes = {row[0] for row in raw_comment_likes}
            
            for comment in comments:
                comment.is_liked_by_me = comment.id in user_comment_likes
        
    return comments

@router.post("/comments/{comment_id}/like")
def like_comment(comment_id: int, db: Session = Depends(get_db), current_user: tables.User = Depends(get_current_user)):
    comment = db.query(tables.Comment).filter(tables.Comment.id == comment_id).first()
    if not comment: raise HTTPException(status_code=404, detail="Comentário não encontrado")
    existing_like = db.query(tables.CommentLike).filter(tables.CommentLike.user_id == current_user.id, tables.CommentLike.comment_id == comment_id).first()
    if existing_like:
        db.delete(existing_like); liked = False
    else:
        new_like = tables.CommentLike(user_id=current_user.id, comment_id=comment_id); db.add(new_like); liked = True
    db.commit(); db.refresh(comment) 
    return {"liked": liked, "total_likes": len(comment.likes)}

@router.post("/memes/{meme_id}/view")
def view_meme(meme_id: int, db: Session = Depends(get_db), current_user: Optional[tables.User] = Depends(get_current_user)):
    if not current_user: return {"message": "Anonymous view ignored"}
    existing_view = db.query(tables.MemeView).filter(tables.MemeView.user_id == current_user.id, tables.MemeView.meme_id == meme_id).first()
    if existing_view: return {"message": "Already viewed"}
    new_view = tables.MemeView(user_id=current_user.id, meme_id=meme_id); db.add(new_view)
    db.query(tables.Meme).filter(tables.Meme.id == meme_id).update({tables.Meme.views: tables.Meme.views + 1})
    db.commit()
    return {"message": "View counted"}

@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, db: Session = Depends(get_db), current_user: tables.User = Depends(get_current_user)):
    comment = db.query(tables.Comment).filter(tables.Comment.id == comment_id).first()
    if not comment: raise HTTPException(status_code=404, detail="Comentário não encontrado")
    if comment.owner_id != current_user.id: raise HTTPException(status_code=403, detail="Sem permissão")
    db.delete(comment); db.commit()
    return {"message": "Deletado"}