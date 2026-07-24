FROM python:3.11-slim

# System deps for XGBoost, asyncpg, Redis
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY services/prediction/ services/prediction/
COPY data/ data/
COPY models/ models/

EXPOSE 8004
CMD ["uvicorn", "services.prediction.main:app", "--host", "0.0.0.0", "--port", "8004"]
