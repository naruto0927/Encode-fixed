FROM python:3.11-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ="Asia/Kolkata"
# gcc is included so pip can build tgcrypto (Pyrogram's fast crypto backend)
# from source on platforms without a prebuilt wheel.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg mediainfo gcc && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["bash", "run.sh"]
