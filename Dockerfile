FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DREAM_API_MODE=mock \
    DREAM_LOG=off \
    HOME=/tmp

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --no-compile --only-binary=:all: -r requirements.txt

COPY src/Backend/ ./
COPY docs/results/ /results-snapshot/

RUN mkdir -p data
RUN chown -R 10001:10001 /app/data

USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
