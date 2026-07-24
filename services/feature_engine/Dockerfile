FROM python:3.11-slim

WORKDIR /app

# Install system deps for asyncpg / numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY data/ data/
COPY models/ models/
COPY services/__init__.py services/__init__.py
COPY services/feature_engine/ services/feature_engine/

EXPOSE 8003
CMD ["uvicorn", "services.feature_engine.main:app", "--host", "0.0.0.0", "--port", "8003"]
