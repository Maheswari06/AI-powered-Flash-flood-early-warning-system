FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY services/scarnet/ services/scarnet/
COPY data/sentinel2/ data/sentinel2/

ENV SCARNET_PORT=8013
ENV SCARNET_DEMO_MODE=true

EXPOSE 8013

CMD ["python", "-m", "uvicorn", "services.scarnet.main:app", "--host", "0.0.0.0", "--port", "8013"]
