FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DREAM_LOG=off \
    HOME=/tmp

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --no-compile --only-binary=:all: -r requirements.txt
COPY src/ ./src/

USER 10001:10001
CMD ["python", "src/test_dream_api.py"]
