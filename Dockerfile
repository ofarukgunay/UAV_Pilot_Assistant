# ==============================================================
# IHA Pilot Asistanı — Dockerfile
# ==============================================================
# Kullanım:
#   docker build -t iha-pilot .
#   docker run -p 5000:5000 --env OLLAMA_BASE_URL=http://host.docker.internal:11434 iha-pilot
# ==============================================================

FROM python:3.11-slim

# Çalışma dizini
WORKDIR /app

# Sistem bağımlılıkları (UTF-8 desteği)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python bağımlılıkları önce kopyala (cache optimizasyonu)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Proje dosyaları
COPY . .

# Log dizini
RUN mkdir -p logs

# Ortam değişkenleri (varsayılan — .env veya docker-compose ile geçersiz kılınabilir)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUTF8=1
ENV OLLAMA_BASE_URL=http://host.docker.internal:11434
ENV OLLAMA_MODEL=llama3.2
ENV WEB_HOST=0.0.0.0
ENV WEB_PORT=5000

# Port aç
EXPOSE 5000

# Sağlık kontrolü
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Başlatma komutu — Web Dashboard
CMD ["python", "src/main.py", "--web"]
