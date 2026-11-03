# Use official lightweight Python runtime
FROM python:3.11-slim

# Prevent Python from writing pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for Docker layer caching
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY backend /app/backend

# Data directory for persistent SQLite database
RUN mkdir -p /app/data

ENV DATABASE_PATH=/app/data/key_finder.db
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

# Health check (supports local port 8000 and dynamic cloud PORT on Render)
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import os, urllib.request; p = os.getenv('PORT', '8000'); urllib.request.urlopen(f'http://localhost:{p}/api/status')" || exit 1

# Start the server using the dynamic PORT environment variable (Render assigns PORT dynamically)
CMD ["sh", "-c", "exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

