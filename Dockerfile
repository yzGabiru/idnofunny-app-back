# ==========================================
# Estágio 1: Builder (Compilação)
# ==========================================
FROM python:3.11-slim as builder

WORKDIR /app

# Variáveis de ambiente para não gerar cache pyc e logs imediatos
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala dependências do sistema necessárias para compilar pacotes Python (se necessário)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Cria um ambiente virtual para isolar as dependências
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copia e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ==========================================
# Estágio 2: Runner (Imagem Final)
# ==========================================
FROM python:3.11-slim

WORKDIR /app

# Variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"

# Instala apenas as bibliotecas de sistema runtime necessárias (libpq para Postgres)
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copia o ambiente virtual do estágio builder
COPY --from=builder /opt/venv /opt/venv

# Copia o código da aplicação
COPY . .

# Cria um usuário não-root por segurança e ajusta permissões
RUN useradd -m appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expondo a porta padrão (informativo)
EXPOSE 8000

# Comando de execução otimizado para Render
# O Render injeta a porta na variável de ambiente PORT.
# O padrão ${PORT:-8000} usa 8000 se a variável não estiver definida (teste local).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]