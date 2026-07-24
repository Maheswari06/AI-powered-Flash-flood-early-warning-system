FROM python:3.11-slim
RUN apt-get update && apt-get install -y sqlite3 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ shared/
COPY services/flood_ledger/ services/flood_ledger/
EXPOSE 8010
CMD ["python", "-m", "services.flood_ledger.main"]
