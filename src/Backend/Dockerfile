FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DREAM_LOG=off \
    HOME=/tmp

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
# Dev-Werkzeuge (pytest, ruff, mypy, watchfiles) sind im Image, damit Tests im Container laufen.
RUN python -m pip install --no-cache-dir --no-compile --only-binary=:all: -r requirements.txt -r requirements-dev.txt
COPY src/Backend/ ./

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
