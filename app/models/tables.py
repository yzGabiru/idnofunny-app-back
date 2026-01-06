from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Table, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

# --- TABELAS DE ASSOCIAÇÃO ---
follows = Table(
    "follows",
    Base.metadata,
    Column("follower_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("followed_id", Integer, ForeignKey("users.id"), primary_key=True)
)

meme_hashtags = Table(
    "meme_hashtags",
    Base.metadata,
    Column("meme_id", Integer, ForeignKey("memes.id"), primary_key=True),
    Column("hashtag_id", Integer, ForeignKey("hashtags.id"), primary_key=True)
)

# Tabela: Likes em Comentários
class CommentLike(Base):
    __tablename__ = "comment_likes"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), primary_key=True)

class MemeView(Base):
    __tablename__ = "meme_views"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    meme_id = Column(Integer, ForeignKey("memes.id"), primary_key=True)

# --- ENTIDADES ---
class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    memes = relationship("Meme", back_populates="category")

class Hashtag(Base):
    __tablename__ = "hashtags"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    memes = relationship("Meme", secondary=meme_hashtags, back_populates="hashtags")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=False)
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    
    # Campo da foto de perfil
    avatar_url = Column(String, nullable=True)
    
    memes = relationship("Meme", back_populates="owner")
    comments = relationship("Comment", back_populates="owner")
    followers = relationship(
        "User", 
        secondary=follows,
        primaryjoin=(follows.c.followed_id == id),
        secondaryjoin=(follows.c.follower_id == id),
        backref="following"
    )

class MemeLike(Base):
    __tablename__ = "meme_likes"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    meme_id = Column(Integer, ForeignKey("memes.id"), primary_key=True)

class Meme(Base):
    __tablename__ = "memes"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    image_url = Column(String)
    media_type = Column(String, default="image") # 'image' ou 'video'
    created_at = Column(DateTime, default=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"))
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    views = Column(Integer, default=0)
    
    # lazy="joined" carrega o usuário junto com o meme (otimização)
    owner = relationship("User", back_populates="memes", lazy="joined")
    
    comments = relationship("Comment", back_populates="meme")
    likes = relationship("MemeLike", backref="meme", cascade="all, delete-orphan")
    category = relationship("Category", back_populates="memes")
    hashtags = relationship("Hashtag", secondary=meme_hashtags, back_populates="memes")

    @property
    def like_count(self):
        return len(self.likes)

    @property
    def owner_username(self):
        return self.owner.username if self.owner else "Anônimo"

    # --- ESSE TEM QUE FICAR (Descomentei) ---
    @property
    def owner_avatar_url(self):
        return self.owner.avatar_url if self.owner else None
    
    # --- ESSE EU REMOVI (Causava o erro) ---
    # @property
    # def owner_is_following(self):
    #    return False

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    text = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"))
    meme_id = Column(Integer, ForeignKey("memes.id"))
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    
    # lazy="joined" carrega o dono do comentário rápido
    owner = relationship("User", back_populates="comments", lazy="joined")
    
    meme = relationship("Meme", back_populates="comments")
    replies = relationship("Comment", back_populates="parent", cascade="all, delete-orphan")
    parent = relationship("Comment", back_populates="replies", remote_side=[id])
    
    likes = relationship("CommentLike", backref="comment", cascade="all, delete-orphan")

    @property
    def owner_username(self):
        return self.owner.username if self.owner else "Anônimo"
    
    @property
    def like_count(self):
        return len(self.likes)

    @property
    def reply_count(self):
        return len(self.replies)

    # --- Pega o avatar do dono do comentário ---
    @property
    def owner_avatar_url(self):
        return self.owner.avatar_url if self.owner else None

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    reason = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    meme_id = Column(Integer, ForeignKey("memes.id"))
    reporter_id = Column(Integer, ForeignKey("users.id"))

    # Relacionamentos (Opcional, se precisar acessar dados do meme/reporter)
    meme = relationship("Meme")
    reporter = relationship("User")