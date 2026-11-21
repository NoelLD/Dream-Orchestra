FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY src/Database/server.py .

EXPOSE 8081
CMD ["python", "server.py"]
