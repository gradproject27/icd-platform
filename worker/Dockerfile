FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY worker.py .

RUN useradd --create-home --uid 10001 icd
USER icd

CMD ["python", "worker.py"]
