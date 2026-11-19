FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Locked dependencies: regenerate with the pip-compile command in the README.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY app ./app
COPY main.py alembic.ini ./
COPY migrations ./migrations

RUN useradd --system --no-create-home --uid 10001 byte     && mkdir data && chown byte data
USER byte

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s     CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/api/v1/health')"

# Plain HTTP inside the compose network: Caddy terminates TLS and forwards the client address.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log",      "--proxy-headers", "--forwarded-allow-ips=*"]
