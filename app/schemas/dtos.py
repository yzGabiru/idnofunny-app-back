from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

# --- USERS & AUTH ---
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    avatar_url: Optional[str] = None
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class EmailVerification(BaseModel):
    email: str
    code: str

class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    memes_count: int = 0
    followers_count: int = 0
    following_count: int = 0
    total_likes: int = 0
    is_following: bool = False
    avatar_url: Optional[str] = None


    class Config:
        from_attributes = True

# --- EXTRAS (CATEGORIA, HASHTAG, LIKE) ---
# Importante: Estas classes devem vir ANTES do MemeResponse

class CategoryResponse(BaseModel):
    id: int
    name: str
    class Config:
        from_attributes = True

class UserPasswordConfirm(BaseModel):
    password: str

class HashtagResponse(BaseModel):
    name: str
    class Config:
        from_attributes = True

class LikeResponse(BaseModel):
    liked: bool
    total_likes: int

# --- COMMENTS & REPORTS ---
class ReportCreate(BaseModel):
    reason: str

class CommentCreate(BaseModel):
    text: str
    parent_id: Optional[int] = None 

class CommentResponse(BaseModel):
    id: int
    text: str
    created_at: datetime
    owner_id: int
    meme_id: int
    owner_username: str = "Anônimo"
    parent_id: Optional[int] = None
    owner_avatar_url: Optional[str] = None
    
    # NOVOS CAMPOS
    like_count: int = 0
    is_liked_by_me: bool = False
    reply_count: int = 0

    class Config:
        from_attributes = True

# --- MEMES ---
class MemeCreate(BaseModel):
    title: str
    media_type: str = "image"

class MemeResponse(BaseModel):
    id: int
    title: str
    image_url: str
    media_type: str = "image"
    created_at: datetime
    owner_id: int
    owner_username: str
    comments: List[CommentResponse] = []
    owner_avatar_url: Optional[str] = None

    like_count: int = 0
    is_liked_by_me: bool = False
    views: int = 0
    owner_is_following: bool = False
    
    # Agora funciona, pois CategoryResponse já foi lido lá em cima
    category: Optional[CategoryResponse] = None
    hashtags: List[HashtagResponse] = []

    class Config:
        from_attributes = True