FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DREAM_LOG=off \
    HOME=/tmp

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --no-compile --only-binary=:all: -r requirements.txt
COPY src/Backend/ ./

USER 10001:10001
EXPOSE 8000
CMD ["python", "server.py"]
