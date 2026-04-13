FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcurl4-openssl-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV LIFE360_CACHE_TTL=30
ENV LIFE360_MAX_RETRIES=5
ENV LIFE360_LOG_LEVEL=DEBUG
ENV LIFE360_HTTP_HOST=0.0.0.0
ENV LIFE360_HTTP_PORT=8123

EXPOSE 8123

CMD ["python", "cli.py", "--http"]