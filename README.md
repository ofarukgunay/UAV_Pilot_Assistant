# IHA Pilot Asistanı

> Doğal dil komutları ile kontrol edilen, güvenlik katmanlı, web dashboard'lu İnsansız Hava Aracı pilot asistanı.

---

## Hızlı Başlangıç (Windows)

```bash
# 1. Repoyu klon'la
git clone https://github.com/ofarukgunay/UAV_Pilot_Assistant.git
cd UAV_Pilot_Assistant

# 2. Ollama'yı başlat (ayrı terminalde)
ollama serve

# 3. Modeli indir (ilk seferinde)
ollama pull llama3.2

# 4. Projeyi başlat
run.bat          # menü açılır → 1 (Docker) veya 2 (Python)
```

Tarayıcıda aç: **http://127.0.0.1:5000**

---

## Gereksinimler

| Araç | Sürüm | İndirme |
|------|-------|---------|
| Python | 3.10+ | [python.org](https://python.org) |
| Ollama | Herhangi | [ollama.com](https://ollama.com) |
| Docker *(opsiyonel)* | 20+ | [docker.com](https://docker.com) |

---

## Çalıştırma Yöntemleri

### Yöntem A: Docker (Önerilen — bağımlılık gerektirmez)

```bash
# Ollama host makinede çalışıyor olmalı
ollama serve

# Docker ile başlat
docker compose up --build
```

### Yöntem B: Python Sanal Ortam

```bash
# Sanal ortam
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Bağımlılıklar
pip install -r requirements.txt

# Web Dashboard
python src/main.py --web

# CLI modu
python src/main.py

# Demo modu (5 otomatik komut)
python src/main.py --demo
```

---

## Proje Yapısı

```
UAV_Pilot_Assistant/
├── src/
│   ├── main.py              # Ana giriş (CLI + web)
│   ├── agent/               # LLM entegrasyonu (Ollama)
│   │   ├── llm_client.py    # Ollama API istemcisi
│   │   ├── command_parser.py # Komut yorumlama + güvenlik onayı
│   │   └── prompts.py       # System prompt şablonları
│   ├── tools/
│   │   └── drone_tools.py   # takeoff, land, go_to, emergency_land...
│   ├── safety/
│   │   ├── validator.py     # Güvenlik doğrulama motoru
│   │   └── rules.py         # 7 güvenlik kuralı (SR-xxx)
│   ├── simulation/
│   │   ├── drone.py         # DroneState veri modeli
│   │   └── environment.py   # Fizik simülasyonu
│   ├── battery/
│   │   └── manager.py       # Batarya yönetimi ve otomatik RTH
│   ├── mission/
│   │   ├── planner.py       # Çok adımlı görev planlama
│   │   └── executor.py      # Görev yürütücüsü
│   ├── logger/
│   │   └── flight_logger.py # JSON/CSV uçuş logu
│   └── web/
│       ├── app.py           # Flask + Socket.IO web dashboard
│       ├── templates/       # HTML şablonları
│       └── static/          # CSS + JS (Leaflet.js harita)
├── config/
│   └── settings.py          # Merkezi yapılandırma
├── tests/                   # 113 pytest testi
├── Dockerfile               # Docker imajı
├── docker-compose.yml       # Docker Compose
├── run.bat                  # Windows hızlı başlatma
└── requirements.txt         # Python bağımlılıkları
```

---

## Desteklenen Komutlar

| Komut Örneği | Eylem |
|---|---|
| "30 metreye kalk" | Kalkış (irtifa doğrulamasıyla) |
| "durum raporu ver" | Telemetri çıkışı |
| "kuzey yönünde 50 metre ilerle" | Koordinat navigasyon |
| "eve dön" | Return-to-Home |
| "iniş yap" | Normal iniş |
| "acil iniş" + "evet" | Kritik eylem onay mekanizması |
| "batarya durumu?" | Batarya seviyesi ve uyarılar |
| "devriye görevi başlat" | Çok adımlı görev zinciri |

---

## Güvenlik Katmanı

- **7 aktif güvenlik kuralı** (SR-BAT-001 → SR-GEO-001)
- Maksimum irtifa sınırı: **120m** (SHGM SHY-İHA-01)
- Geofence yarıçapı: **500m**
- Kritik komutlar (**acil iniş**, **motor durdur**) için iki aşamalı onay
- Düşük bataryada otomatik **Return-to-Home**

---

## Test

```bash
# Tüm testler (113 test)
pytest tests/ -v

# Kapsam raporu
pytest tests/ --cov=src --cov-report=html
```

---

## Konfigürasyon

`.env.example` dosyasını `.env` olarak kopyalayıp düzenle:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
OLLAMA_TIMEOUT=120
WEB_PORT=5000
```

---

## Geliştirici Notları

Detaylı geliştirici rehberi için: [GELISTIRICI_TALIMATLARI.md](GELISTIRICI_TALIMATLARI.md)

---

**Ömer Faruk Günay** — 2025–2026
