FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Locked dependencies: regenerate with the pip-compile command in the README.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY app ./app
COPY main.py ./

RUN useradd --system --no-create-home --uid 10001 byte
USER byte

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import os, ssl, urllib.request as u; tls = os.environ.get('BYTE_TLS_CERT'); u.urlopen(('https' if tls else 'http') + '://localhost:8000/api/v1/health', context=ssl._create_unverified_context() if tls else None)"

# TLS is on when BYTE_TLS_CERT and BYTE_TLS_KEY are set (required for LAN exposure).
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port 8000 ${BYTE_TLS_CERT:+--ssl-certfile \"$BYTE_TLS_CERT\" --ssl-keyfile \"$BYTE_TLS_KEY\"}"]
