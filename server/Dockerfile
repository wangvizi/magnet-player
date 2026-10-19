FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    DATA_DIR=/data \
    RPC_SECRET=magnetplayer \
    API_KEY= \
    ARIA2_PORT=6800

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip ffmpeg aria2 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
