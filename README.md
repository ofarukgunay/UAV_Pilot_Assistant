# IHA Pilot Asistanı 🛩️

> **LLM Tabanlı İnsansız Hava Aracı Pilot Asistan Sistemi**  
> Doğal dil komutlarını yorumlayan, çok adımlı görev planlayan ve açıklanabilir güvenlik uygulayan bir İHA pilot prototipi.

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-106%20passed-brightgreen)](#testler)
[![LLM](https://img.shields.io/badge/LLM-Ollama%20(yerel)-orange)](#kurulum)
[![License](https://img.shields.io/badge/Lisans-Eğitim-lightgrey)](#lisans)

---

## 📋 Proje Özeti

IHA Pilot Asistanı, operatörlerin **doğal dil komutlarıyla** simüle edilmiş bir insansız hava aracını güvenli şekilde yönetmesine olanak tanır. Sistem, yapay zekanın her kararını **SHGM/ICAO/FAA referanslı güvenlik kurallarıyla** doğrular ve gerekçelendirir.

### 5 Özgün Özellik

| # | Özellik | Açıklama |
|---|---------|----------|
| 🌐 | **Web Dashboard** | Flask + Leaflet.js gerçek zamanlı izleme |
| 🗂️ | **Çok Adımlı Görev Planlama** | Tek cümle → güvenli görev zinciri |
| 🔋 | **Akıllı Batarya Yönetimi** | 4 seviyeli uyarı + otomatik RTH |
| 🧠 | **Açıklanabilir Güvenlik** | Her karar gerekçeli, 10 SHGM/FAA kuralı |
| 📊 | **Otomatik Test Raporu** | JSON + CSV + renk kodlu HTML |

---

## 🏗️ Mimari

```
Kullanıcı (Doğal Dil)
       ↓
Ollama LLM (llama3 / yerel)
       ↓
SafetyValidator (10 SHGM/ICAO/FAA kuralı)
       ↓
DroneTools (takeoff / land / go_to / RTH)
       ↓
PhysicsEngine (nokta-kütlesi simülasyon)
       ↓
FlightLogger (JSON + CSV + HTML rapor)
```

---

## 📂 Dizin Yapısı

```
UAV_Pilot_Assistant/
├── src/
│   ├── main.py              # Giriş noktası (CLI / Web / Demo)
│   ├── simulation/          # DroneState, PhysicsEngine, Telemetri
│   ├── agent/               # Ollama LLM istemcisi, prompt, parser
│   ├── tools/               # 5 güvenli araç fonksiyonu
│   ├── safety/              # 10 kural, SafetyValidator
│   ├── battery/             # Akıllı batarya yöneticisi
│   ├── mission/             # Görev planlayıcı & yürütücü
│   ├── logger/              # Tri-format loglama + HTML rapor
│   └── web/                 # Flask dashboard + Leaflet.js
├── tests/                   # 106 pytest testi
├── docs/                    # Teknik rapor, kurulum kılavuzu
├── config/                  # Merkezi yapılandırma (frozen dataclass)
├── logs/                    # Uçuş logları (git'e gitmez)
├── requirements.txt
└── .env.example
```

---

## ⚡ Hızlı Başlangıç

### 1. Kurulum

```bash
# Sanal ortam oluştur
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# Bağımlılıkları kur
pip install -r requirements.txt

# Ortam değişkenlerini ayarla (isteğe bağlı)
copy .env.example .env
```

### 2. Ollama Başlat (Ayrı terminalde)

```bash
ollama serve
ollama pull llama3     # ~4.7 GB — bir kere indir
```

### 3. Çalıştır

```bash
# İnteraktif CLI
python src/main.py

# Demo modu (8 hazır komut, video kaydı için ideal)
python src/main.py --demo

# Web Dashboard
python src/main.py --web
# → http://127.0.0.1:5000
```

---

## 🛡️ Güvenlik Kuralları

| Kural ID | Kural | Şiddet | Referans |
|----------|-------|--------|----------|
| SR-BAT-001 | Acil batarya seviyesi | CRITICAL | FAA AC 107-2B |
| SR-BAT-002 | RTH batarya eşiği (%20) | ERROR | SHGM SHY-İHA-01 |
| SR-ALT-001 | Maks. irtifa (120m AGL) | ERROR | ICAO Annex 2 |
| SR-ALT-002 | Min. kalkış irtifası | ERROR | Operasyonel |
| SR-ALT-003 | Tek komut maks. kalkış | WARNING | Operasyonel |
| SR-FLT-001 | Havadayken kalkış engeli | ERROR | Operasyonel |
| SR-FLT-002 | Yerdeyken iniş/RTH engeli | ERROR | Operasyonel |
| SR-GEO-001 | Geofence ihlali (500m) | ERROR | SHGM limitleri |
| SR-GEO-002 | go_to maks. irtifa | ERROR | SHGM SHY-İHA-01 |
| SR-GEO-003 | go_to min. irtifa | ERROR | Fiziksel kısıt |

---

## 🧪 Testler

```bash
python -m pytest tests/ -v
# Beklenen: 106 passed ✅
```

| Test Grubu | Sayı |
|-----------|------|
| Simülasyon (drone, fizik, telemetri) | 20 |
| Güvenlik (10 kural ayrı ayrı) | 30 |
| Araç fonksiyonları (5 araç) | 31 |
| Görev + Batarya | 18 |
| Komut parser entegrasyon | 17 |
| **Toplam** | **106** |

---

## 📚 Dokümantasyon

- [Teknik Rapor](docs/technical_report.md) — Mimari, güvenlik, test sonuçları
- [Kurulum Kılavuzu](docs/INSTALLATION.md) — Adım adım kurulum
- [Geliştirici Talimatları](GELISTIRICI_TALIMATLARI.md) — Proje gereksinimleri

---

## 🔧 Yapılandırma

`.env` dosyası ile özelleştirilebilir:

```env
OLLAMA_MODEL=llama3          # veya qwen2.5, mistral, vb.
OLLAMA_BASE_URL=http://localhost:11434
FLASK_SECRET_KEY=gizli-anahtar
WEB_PORT=5000
```

---

## ⚠️ Sınırlılıklar

- Gerçek rotor aerodinamiği modellenmemiştir (nokta-kütlesi simülasyon)
- LLM JSON modu zorunludur — küçük modeller bazen schema dışı yanıt üretebilir
- Gerçek GPS/WGS84 koordinat sistemi değil, metre bazlı NED kullanılır
- Tek kullanıcı/oturum tasarımı

---

## 📜 Lisans

Bu proje eğitim amaçlı geliştirilmiştir.  
Güvenlik referansları: **SHGM SHY-İHA-01**, **ICAO Annex 2**, **FAA AC 107-2B**, **STANAG 4586**
