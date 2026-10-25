# =====================================================================
# VyaparMitra - Production Multi-Stage Dockerfile
# =====================================================================

# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Runtime Backend & App Server
FROM python:3.11-slim AS runner

# Install Coin-OR CBC solver and curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    coinor-cbc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application, sample data, and evaluation cache
COPY backend/ ./backend/
COPY data/ ./data/

# Copy built frontend assets from stage 1
COPY --from=frontend-builder /app/dist ./dist

ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DEBUG=False

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/v1/health || exit 1

# Start uvicorn server (honors dynamic PORT assigned by cloud hosts like Render/Railway)
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
