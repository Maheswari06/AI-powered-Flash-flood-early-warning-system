FROM python:3.11-slim

# System deps for SQLite, audio
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 alsa-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY services/acn_node/ services/acn_node/
COPY data/ data/
COPY models/ models/

EXPOSE 8006
CMD ["python", "-m", "services.acn_node.acn_node", "--node", "majuli"]
