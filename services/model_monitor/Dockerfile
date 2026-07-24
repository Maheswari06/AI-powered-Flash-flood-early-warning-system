FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY services/model_monitor/ services/model_monitor/

ENV PYTHONPATH=/app
ENV DEMO_MODE=true

EXPOSE 8014
CMD ["python", "-m", "services.model_monitor.main"]
