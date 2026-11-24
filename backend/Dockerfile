FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ssh and scp for the hpc_batch analysis backend (C1 decision F4, app/hpc/batch.py).
RUN apt-get update \
    && apt-get install --yes --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# /data/uploads is the shared uploads volume; a new named volume takes this owner.
RUN useradd --create-home --uid 10001 icd && mkdir -p /data/uploads && chown icd /data/uploads
USER icd

EXPOSE 8000
# Apply migrations, then replace the shell with uvicorn so it receives signals directly.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
