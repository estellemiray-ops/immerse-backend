# Deno is the JavaScript runtime current yt-dlp needs to solve YouTube's player challenges
FROM denoland/deno:bin AS deno

FROM python:3.12-slim

COPY --from=deno /deno /usr/local/bin/deno

# ffmpeg is needed by yt-dlp to extract audio for the Whisper fallback path
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
