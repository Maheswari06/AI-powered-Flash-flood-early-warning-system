FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY services/alert_dispatcher/ services/alert_dispatcher/

EXPOSE 8005
CMD ["uvicorn", "services.alert_dispatcher.main:app", "--host", "0.0.0.0", "--port", "8005"]
