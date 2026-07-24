FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY services/api_gateway/ services/api_gateway/

ENV GATEWAY_PORT=8000
ENV GATEWAY_CACHE_TTL=30

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "services.api_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
