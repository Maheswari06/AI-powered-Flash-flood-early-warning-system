FROM python:3.11-slim

# System deps for audio processing and NLP
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY services/chorus/ services/chorus/
COPY data/ data/

EXPOSE 8008
CMD ["python", "-m", "services.chorus.main"]
