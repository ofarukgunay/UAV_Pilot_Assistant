# IHA Pilot Asistanı — Kurulum Kılavuzu

> LLM Tabanlı İnsansız Hava Aracı Pilot Asistan Sistemi  
> **Başka biri kurabilmeli** prensibiyle hazırlanmıştır.

## Gereksinimler

| Bileşen | Minimum | Önerilen |
|---------|---------|----------|
| Python | 3.10+ | 3.11+ |
| RAM | 8 GB | 16 GB |
| GPU | - | NVIDIA (LLM hızlandırma) |
| İşletim Sistemi | Windows 10 / Ubuntu 20.04 / macOS 12 |

## 1. Depoyu Klonla

```bash
git clone https://github.com/ofarukgunay/UAV_Pilot_Assistant.git
cd UAV_Pilot_Assistant
```

## 2. Python Ortamı Oluştur

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

## 3. Bağımlılıkları Kur

```bash
pip install -r requirements.txt
```

## 4. Ortam Değişkenlerini Ayarla

```bash
cp .env.example .env
# .env dosyasını düzenle (isteğe bağlı, varsayılanlar çalışır)
```

## 5. Ollama Kur ve Başlat

```bash
# Ollama yükle: https://ollama.com
# Sonra:
ollama serve         # Terminalde çalışır bırak
ollama pull llama3   # Modeli indir (~4.7 GB)
```

## 6. Sistemi Çalıştır

### CLI Modu (Standart)
```bash
python src/main.py
```

### Demo Modu (Video çekimi için)
```bash
python src/main.py --demo
```

### Web Dashboard
```bash
python src/main.py --web
# Tarayıcıda: http://127.0.0.1:5000
```

### Testleri Çalıştır
```bash
python -m pytest tests/ -v
# Beklenen: 106 passed
```

## Sorun Giderme

| Sorun | Çözüm |
|-------|-------|
| `ConnectionError` | `ollama serve` çalıştır |
| `ModuleNotFoundError` | `pip install -r requirements.txt` tekrarla |
| Model yok | `ollama pull llama3` |
| Port 5000 meşgul | `.env` içinde `WEB_PORT=5001` ayarla |
