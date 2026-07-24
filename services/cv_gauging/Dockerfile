FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY services/cv_gauging/ services/cv_gauging/
COPY data/ data/
COPY models/ models/

EXPOSE 8002
CMD ["uvicorn", "services.cv_gauging.main:app", "--host", "0.0.0.0", "--port", "8002"]
