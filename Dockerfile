# ColsTorso – single-container deploy (FastAPI + SQLite). ~60 MB RAM idle.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PORT=8000 COLSTORSO_DB=/data/colstorso.db COLSTORSO_PUBLIC_DEMO=1 COLSTORSO_AUTO_SEED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -r -u 10001 app && mkdir -p /data && chown app /data
COPY colstorso ./colstorso
COPY static ./static
COPY design/tokens.css design/logo*.svg design/wordmark.svg ./design/
COPY design/fonts ./design/fonts
COPY design/icons ./design/icons
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health',timeout=4).status==200 else 1)"
# one worker: SQLite + in-process rate limiter; plenty for 1-5 operators plus demo visitors
CMD ["sh", "-c", "exec uvicorn colstorso.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
