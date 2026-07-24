FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ shared/
COPY services/federated_server/ services/federated_server/
COPY data/ data/
EXPOSE 8009 8080
CMD ["python", "-m", "services.federated_server.main"]
