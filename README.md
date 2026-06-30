# IHA Pilot Asistanı 🛩️

Büyük Dil Modeli (LLM) tabanlı İHA pilot asistanı. Doğal dil komutlarını yorumlayan, telemetri okuyan, güvenlik kontrolü yapan ve test edilmiş bir pilot asistanı prototipi.

## Proje Yapısı

```
IHA_Pilot_Asistani/
├── src/                         # Ana kaynak kodu
│   ├── main.py                  # Giriş noktası (CLI)
│   ├── simulation/              # Drone simülasyonu ve telemetri
│   ├── agent/                   # LLM agent katmanı
│   ├── tools/                   # Güvenli araç fonksiyonları
│   ├── safety/                  # Güvenlik doğrulama katmanı
│   └── logger/                  # Kayıt sistemi
├── tests/                       # Test dosyaları
├── logs/                        # Çalışma zamanı logları
├── config/                      # Yapılandırma dosyaları
└── docs/                        # Dokümantasyon
```

## Hızlı Başlangıç

Detaylı kurulum adımları için [GELISTIRICI_TALIMATLARI.md](./GELISTIRICI_TALIMATLARI.md) dosyasına bakın.

```bash
# 1. Sanal ortam oluştur
python -m venv venv
venv\Scripts\activate        # Windows

# 2. Bağımlılıkları kur
pip install -r requirements.txt

# 3. Ortam değişkenlerini ayarla
copy .env.example .env       # .env dosyasını düzenle

# 4. Çalıştır
python src/main.py
```

## Lisans

Bu proje eğitim amaçlıdır.
