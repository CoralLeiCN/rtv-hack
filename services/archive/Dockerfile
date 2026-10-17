FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/archive /app/services/archive
RUN pip install --no-cache-dir './services/archive[models]'
ENV MEDIA_ROOT=/media
EXPOSE 18001
CMD ["video-archive", "serve", "--host", "0.0.0.0"]
