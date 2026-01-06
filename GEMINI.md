# IDNOFunny Pro - Developer Context (GEMINI.md)

This file contains the context, architecture, and conventions for the IDNOFunny Pro project. Refer to this whenever making changes to ensure consistency.

## 1. Project Overview
IDNOFunny Pro is a meme sharing platform built with FastAPI (Backend) and likely a separate frontend (not fully visible here, but `static_ui` suggests some presence). It allows users to upload memes, comment, like, follow others, and explore content via categories and hashtags.

## 2. Technology Stack
- **Language:** Python 3.11
- **Framework:** FastAPI
- **Database:** PostgreSQL 15 (via SQLAlchemy ORM & psycopg2)
- **Cache/Rate Limiting:** Redis (via `fastapi-limiter`)
- **Authentication:** OAuth2 with Password Bearer (JWT)
- **Image Processing:** Pillow (PIL)
- **Migrations:** Alembic (configured in `requirements.txt` but tables currently created via `Base.metadata.create_all`)
- **Containerization:** Podman & podman-compose

## 3. Project Structure
```
/
├── app/
│   ├── core/           # Security, dependencies, config
│   ├── models/         # SQLAlchemy database models (tables.py)
│   ├── routers/        # API endpoints (auth, memes, users)
│   ├── schemas/        # Pydantic DTOs for request/response
│   ├── database.py     # Database connection & session handling
│   └── main.py         # App entry point, middleware, startup logic
├── uploads/            # Stored user content (images/avatars)
├── docker-compose.yml  # Service orchestration
├── Dockerfile          # API image build
└── requirements.txt    # Python dependencies
```

## 4. Database Schema (Key Models)
Defined in `app/models/tables.py`.

- **User:** `id`, `username`, `email`, `hashed_password`, `avatar_url`, `is_active`.
- **Meme:** `id`, `title`, `image_url`, `owner_id`, `category_id`, `views`, `created_at`.
- **Comment:** `id`, `text`, `owner_id`, `meme_id`, `parent_id` (recursive for replies).
- **Category:** `id`, `name`.
- **Hashtag:** `id`, `name` (Many-to-Many with Memes).
- **Interactions:**
    - `MemeLike` (User <-> Meme)
    - `CommentLike` (User <-> Comment)
    - `MemeView` (User <-> Meme, unique view tracking)
    - `Follows` (User <-> User, self-referential)

## 5. API Architecture

### Authentication
- **Flow:** OAuth2 Password Bearer (`/token` implied, though defined in routers).
- **Token:** JWT (HS256) containing `sub` (username).
- **Hashing:** Bcrypt.
- **Dependency:** `get_current_user` injects the authenticated `User` object.

### Key Features
- **Rate Limiting:** Implemented via `fastapi-limiter` (Redis backend).
    - Memes: 1 per 60s.
    - Comments: 1 per 1s.
- **Image Processing:**
    - Validates Magic Bytes (JPEG/PNG).
    - Converts to RGB/JPEG.
    - Strips EXIF metadata.
    - Saves to local `uploads/` directory.
- **Content Safety:**
    - `better_profanity` used for comment filtering.
    - Anti-spam check: prevents duplicate comments and rapid-fire posting.

## 6. Development Workflow

### Running with Podman
```bash
podman-compose up --build
```
- **API:** http://localhost:8000
- **Docs:** http://localhost:8000/docs
- **DB:** Port 5432
- **Redis:** Port 6379

### Local Environment
- Requires `.env` file (loaded by `python-dotenv`).
- Static files served at `/static` (mapped to `uploads/`).

## 7. Conventions & Guidelines
- **DTOs:** Use Pydantic models in `app/schemas/dtos.py` for all I/O. Use `Config: from_attributes = True` for ORM compatibility.
- **Dependency Injection:** Use `Depends(get_db)` for database sessions.
- **Async:** Redis operations are async; Database operations are currently synchronous (standard SQLAlchemy session).
- **Formatting:** Follow PEP 8.
- **Safety:** Always validate file uploads and user input. Use parameterized queries (handled by ORM).
