# IHA Pilot Asistanı — Teknik Rapor

> **Proje:** LLM Tabanlı İnsansız Hava Aracı Pilot Asistan Sistemi  
> **Versiyon:** 1.0  
> **Tarih:** Temmuz 2025  
> **Uyum:** SHGM SHY-İHA-01 | ICAO Annex 2 | FAA AC 107-2B | STANAG 4586

---

## 1. Sistem Genel Bakış

IHA Pilot Asistanı, Ollama yerel LLM entegrasyonu kullanarak operatörlerin doğal dil komutlarıyla simüle edilmiş bir insansız hava aracını güvenli şekilde yönetmelerini sağlayan bir sistemdir. Sistem, yalnızca önceden tanımlanmış araç fonksiyonlarına erişime izin veren **katmanlı güvenlik mimarisi** ile tasarlanmıştır.

### 1.1 Temel Özellikler

| Özellik | Açıklama |
|---------|----------|
| 🤖 LLM Entegrasyonu | Ollama yerel model (llama3, qwen, vb.) JSON çıktı modu |
| 🛡️ Açıklanabilir Güvenlik | 10 SHGM/ICAO referanslı kural, her karar gerekçeli |
| 🗂️ Görev Planlama | Tek cümle → çok adımlı güvenli görev zinciri |
| 🔋 Akıllı Batarya | 4 seviyeli uyarı + otomatik RTH + gidiş-dönüş enerji hesabı |
| 🌐 Web Dashboard | Flask + Leaflet.js gerçek zamanlı izleme |
| 📊 Test Loglama | JSON + CSV + renk kodlu HTML rapor |

---

## 2. Sistem Mimarisi

### 2.1 Katmanlı Mimari

```
┌────────────────────────────────────────────────────┐
│                  KULLANICI ARAYÜZÜ                 │
│            CLI / Web Dashboard (Flask)             │
└───────────────────────┬────────────────────────────┘
                        │ Doğal dil komutu
┌───────────────────────▼────────────────────────────┐
│                   LLM KATMANI                      │
│          Ollama (llama3) — JSON Format Mod         │
│  Sistem Promptu: 4400 karakter, 3 tam örnek        │
│  Çıktı: action + parameters + reasoning + conf.    │
└───────────────────────┬────────────────────────────┘
                        │ ParsedCommand
┌───────────────────────▼────────────────────────────┐
│              GÜVENLİK KATMANI (Faz 2)             │
│         SafetyValidator + SAFETY_RULES             │
│  10 kural | SHGM SHY-İHA-01 | FAA AC 107-2B       │
│  Karar: is_valid + rule_violated + reason          │
└───────────────────────┬────────────────────────────┘
                        │ ValidationResult (valid)
┌───────────────────────▼────────────────────────────┐
│                ARAÇ KATMANI (Faz 1)               │
│     DroneTools: takeoff / land / go_to / RTH       │
│  İkinci savunma katmanı + ToolResult üretimi       │
└───────────────────────┬────────────────────────────┘
                        │ ToolResult
┌───────────────────────▼────────────────────────────┐
│           FİZİK SİMÜLASYON KATMANI               │
│  PhysicsEngine: Nokta-kütlesi modeli              │
│  DroneState: Tek bilgi kaynağı (SSOT)             │
└────────────────────────────────────────────────────┘
```

### 2.2 Dizin Yapısı

```
UAV_Pilot_Assistant/
├── config/
│   └── settings.py          # Frozen dataclass yapılandırma
├── src/
│   ├── simulation/
│   │   ├── drone.py          # DroneState + FlightMode
│   │   ├── environment.py    # PhysicsEngine
│   │   └── telemetry.py      # TelemetryReader
│   ├── tools/
│   │   └── drone_tools.py    # 5 güvenli araç fonksiyonu
│   ├── safety/
│   │   ├── rules.py          # 10 SHGM/ICAO/FAA referanslı kural
│   │   └── validator.py      # Açıklanabilir SafetyValidator
│   ├── agent/
│   │   ├── prompts.py        # 4400+ karakter sistem promptu
│   │   ├── llm_client.py     # Ollama HTTP istemcisi
│   │   └── command_parser.py # LLM→Güvenlik→Araç köprüsü
│   ├── battery/
│   │   └── manager.py        # 4 seviyeli batarya izleme
│   ├── mission/
│   │   ├── planner.py        # Görev oluşturma + doğrulama
│   │   └── executor.py       # Adım adım yürütme
│   ├── logger/
│   │   └── flight_logger.py  # JSON + CSV + HTML rapor
│   ├── web/
│   │   ├── app.py            # Flask + SocketIO API
│   │   ├── templates/        # Leaflet dashboard HTML
│   │   └── static/           # CSS + JS
│   └── main.py               # CLI / Web / Demo giriş noktası
├── tests/                    # 106 pytest testi
├── docs/                     # Teknik rapor, test sonuçları
└── requirements.txt
```

---

## 3. Güvenlik Mimarisi

### 3.1 Derinlemesine Savunma (Defense in Depth)

Sistem, NASA/ESA güvenlik felsefesini benimseyen üç bağımsız güvenlik katmanı uygular:

| Katman | Bileşen | Açıklama |
|--------|---------|----------|
| 1. | `SAFETY_RULES` | Kural tanım katmanı — SHGM/FAA referanslı |
| 2. | `SafetyValidator` | Kural uygulama katmanı — her komut için |
| 3. | `DroneTools` | Araç seviyesi ön doğrulama — ikinci bağımsız kontrol |

### 3.2 Aktif Güvenlik Kuralları

| Kural ID | Kural Adı | Şiddet | Yasal Referans |
|----------|-----------|--------|----------------|
| SR-BAT-001 | Acil Batarya Seviyesi | CRITICAL | FAA AC 107-2B §6.3.1 |
| SR-BAT-002 | RTH Batarya Eşiği | ERROR | SHGM SHY-İHA-01 §5.4.2 |
| SR-ALT-001 | Maksimum İrtifa (120m) | ERROR | SHGM SHY-İHA-01 §5.1.3 / ICAO Annex 2 |
| SR-ALT-002 | Minimum Kalkış İrtifası | ERROR | Operasyonel standart |
| SR-ALT-003 | Tek Komut Maks. Kalkış | WARNING | Operasyonel prosedür |
| SR-FLT-001 | Havadayken Kalkış Engeli | ERROR | Operasyonel prosedür |
| SR-FLT-002 | Yerdeyken İniş/RTH Engeli | ERROR | Operasyonel prosedür |
| SR-GEO-001 | Geofence İhlali (500m) | ERROR | SHGM operasyonel sınırlar |
| SR-GEO-002 | go_to Maks. İrtifa | ERROR | SHGM SHY-İHA-01 §5.1.3 |
| SR-GEO-003 | go_to Minimum İrtifa | ERROR | Fiziksel kısıt |

### 3.3 Açıklanabilirlik (Explainability)

Her güvenlik kararı için:
- **İhlal edilen kural kodu** (örn: `SR-ALT-001`)
- **Türkçe gerekçe** (neden reddedildi)
- **Yasal referans** (hangi yönetmelik)
- **Kullanıcı önerisi** (ne yapabilir)

Bu tasarım, EASA AI Roadmap 2.0 (2023) Explainability Requirements'a uygundur.

---

## 4. LLM Entegrasyonu

### 4.1 Ollama Konfigürasyonu

- **Model:** `llama3` (varsayılan, değiştirilebilir)
- **Mod:** JSON format (`"format": "json"`)
- **Sıcaklık:** 0.1 (deterministik, güvenilir çıktı)
- **Endpoint:** `POST http://localhost:11434/api/generate`

### 4.2 Prompt Mimarisi

```
Sistem Promptu (4443 karakter):
  [Persona] → İHA Pilot Asistanı rolü
  [Kısıtlamalar] → 5 kesin yasak
  [Drone Durumu] → TelemetryReader.get_llm_context()
  [Araçlar] → 8 eylem, her biri açıklamalı
  [Format] → JSON şeması + 3 tam örnek
```

### 4.3 JSON Çıktı Şeması

```json
{
  "action": "takeoff|land|return_to_home|go_to|get_telemetry|plan_mission|clarify|reject",
  "parameters": {},
  "reasoning": "Neden bu eylem (Türkçe açıklama)",
  "confidence": 0.95,
  "needs_clarification": false,
  "clarification_question": "",
  "safety_note": "Önemli güvenlik notu"
}
```

### 4.4 Hata Yönetimi (Graceful Degradation)

| Hata Durumu | Sistem Yanıtı |
|-------------|---------------|
| Ollama kapalı | Açık hata mesajı + `ollama serve` yönlendirmesi |
| JSON parse hatası | Ham yanıt loglanır + güvenli `clarify` döndürülür |
| Bilinmeyen eylem | `reject` ile güvenli geri dön |
| Timeout | Kullanıcıya bilgi + tekrar deneme önerisi |

---

## 5. Özgün Özellikler

### 5.1 🌐 Web Dashboard (Flask + Leaflet.js)

- **REST API:** `/api/state`, `/api/command`, `/api/logs`, `/api/stats`
- **WebSocket:** Her saniye telemetri push (Flask-SocketIO)
- **Harita:** Leaflet.js — drone konumu gerçek zamanlı, iz çizgisi
- **Görsel:** Batarya/irtifa göstergeleri, LLM analiz kutusu, komut geçmişi

### 5.2 🗂️ Çok Adımlı Görev Planlama

```
Kullanıcı: "30m kalk, 100m doğuya git, durum bildir, eve dön"
    ↓
LLM: plan_mission → 4 adımlı görev planı
    ↓
MissionPlanner: Toplu güvenlik doğrulaması
    ↓
MissionExecutor: Adım adım yürütme + durum makina
    ↓
Terminal: İlerleme çubuğu + her adım sonucu
```

**Durum Makinesi:** `PENDING → RUNNING → COMPLETED / FAILED / ABORTED`

### 5.3 🔋 Akıllı Batarya Yönetimi

- **4 seviye:** NORMAL → LOW → CRITICAL → EMERGENCY
- **Enerji hesabı:** Gidiş + dönüş mesafesi bazlı `go_to` engeli
- **Otomatik RTH:** %20 altında havadaysa tetiklenir
- **Kalan süre tahmini:** Hover tüketimi bazlı hesap

### 5.4 🧠 Açıklanabilir Güvenlik

Her karar terminalde ve web dashboard'da görünür:
```
❌ GÜVENLİK REDDİ [ERROR]
   Eylem        : takeoff
   İhlal Kuralı : SR-ALT-001
   Gerekçe      : Hedef irtifa 5000m > maksimum izinli 120m AGL.
   Öneri        : İrtifayı 120m veya altına düşürün.
   Yasal Ref.   : SHGM SHY-İHA-01 §5.1.3 / ICAO Annex 2
```

### 5.5 📊 Otomatik Test Raporu

FlightLogger üç formatta rapor üretir:
- **JSON:** Makine okunabilir, tüm meta verilerle
- **CSV:** Excel/pandas ile analiz edilebilir
- **HTML:** Renk kodlu (yeşil/kırmızı/sarı), istatistik özeti, eylem dağılımı

---

## 6. Test Sonuçları

### 6.1 Özet

| Kategori | Test Sayısı | Geçen |
|----------|------------|-------|
| Simülasyon (drone, fizik, telemetri) | 20 | 20 |
| Güvenlik katmanı (10 kural) | 30 | 30 |
| Araç fonksiyonları (5 araç) | 31 | 31 |
| Görev + Batarya yönetimi | 18 | 18 |
| Komut parser entegrasyon | 17 | 17 |
| **TOPLAM** | **106** | **106** |

**Başarı Oranı: %100**

### 6.2 Önemli Test Senaryoları

| Senaryo | Beklenen | Sonuç |
|---------|----------|-------|
| `takeoff(5000m)` → `SR-ALT-001` reddi | ❌ Reddedildi | ✅ |
| `takeoff(-5m)` → `SR-ALT-002` reddi | ❌ Reddedildi | ✅ |
| Yerde iken `land()` → `SR-FLT-002` | ❌ Reddedildi | ✅ |
| Havada iken tekrar `takeoff()` | ❌ Reddedildi | ✅ |
| Geofence dışı `go_to(600m, 0)` | ❌ Reddedildi | ✅ |
| Batarya %12 → `SR-BAT-001` | ❌ Reddedildi | ✅ |
| `takeoff(30m)` → başarılı kalkış | ✅ Başarılı | ✅ |
| `go_to` → konum doğru güncellendi | ✅ Başarılı | ✅ |
| RTH → eve döndü, indi | ✅ Başarılı | ✅ |
| Clone bağımsızlığı | ✅ Bağımsız | ✅ |

---

## 7. Sınırlılıklar

| Sınırlılık | Açıklama |
|------------|----------|
| **Simülasyon basitliği** | Gerçek rotor aerodinamiği, rüzgar, hava direnci modellenmedi |
| **LLM güvenilirliği** | Ollama JSON modu zorunlu; bazı küçük modeller bazen schema dışı yanıt üretir |
| **Koordinat sistemi** | NED (metre bazlı), gerçek GPS/WGS84 koordinatlarına dönüşüm eklenmedi |
| **Eş zamanlı kontrol** | Tek kullanıcı / tek oturum tasarımı |
| **Gerçek zamanlı sensör** | Fizik motoru zaman bazlı tick yerine anlık geçiş simülasyonu |
| **İnternet bağımlılığı** | Web dashboard Google Fonts ve Leaflet CDN kullanır |

---

## 8. Yasal Uyum Referansları

| Standart | Kapsam | Kullanım |
|----------|--------|----------|
| SHGM SHY-İHA-01 | Türkiye İHA yönetmeliği | İrtifa, alan ve batarya limitleri |
| ICAO Annex 2 | Uçuş kuralları | 120m AGL maksimum irtifa |
| FAA AC 107-2B | Küçük İHA sistemleri | Batarya güvenlik rezervi |
| STANAG 4586 | NATO İHA birlikte çalışabilirlik | Araç/kontrol arayüzü tasarımı |
| EASA AI Roadmap 2.0 | Yapay zeka açıklanabilirlik | Güvenlik kararı gerekçelendirme |

---

## 9. Çalıştırma

```bash
# Bağımlılıkları kur
pip install -r requirements.txt

# Ollama başlat (ayrı terminalde)
ollama serve
ollama pull llama3

# CLI modu
python src/main.py

# Demo modu (otomatik 8 komut)
python src/main.py --demo

# Web dashboard
python src/main.py --web
# → http://127.0.0.1:5000

# Testler
python -m pytest tests/ -v
```
