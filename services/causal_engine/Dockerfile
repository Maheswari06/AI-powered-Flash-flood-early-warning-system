FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ shared/
COPY services/causal_engine/ services/causal_engine/
EXPOSE 8007
CMD ["python", "-m", "services.causal_engine.main"]
