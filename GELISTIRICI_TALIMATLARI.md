# 🚀 Geliştirici Talimatları — IHA Pilot Asistanı

Bu dosya, projeye yeni başlayan bir geliştiricinin adım adım yapması gerekenleri açıklar.

---

## 📋 Ön Gereksinimler

Projeye başlamadan önce aşağıdakilerin bilgisayarında kurulu olduğundan emin ol:

| Araç | Minimum Versiyon | Kontrol Komutu |
|------|------------------|----------------|
| Python | 3.10+ | `python --version` |
| pip | 21+ | `pip --version` |
| Git | 2.30+ | `git --version` |

---

## 1️⃣ Adım: Repoyu Klonla veya Aç

Eğer repo zaten bilgisayarındaysa bu adımı atla.

```bash
git clone <repo-url>
cd IHA_Pilot_Asistani
```

---

## 2️⃣ Adım: Sanal Ortam (Virtual Environment) Oluştur

Her zaman sanal ortam içinde çalış. Bu, bağımlılıkların sistemini bozmasını engeller.

```bash
# Sanal ortam oluştur
python -m venv venv

# Sanal ortamı aktifleştir
# Windows:
venv\Scripts\activate

# macOS/Linux:
# source venv/bin/activate
```

> ⚠️ Terminal'de `(venv)` yazısını görmelisin. Görmüyorsan sanal ortam aktif değil demektir.

---

## 3️⃣ Adım: Bağımlılıkları Kur

```bash
pip install -r requirements.txt
```

---

## 4️⃣ Adım: LLM API Anahtarını Ayarla

Bu proje bir büyük dil modeli (LLM) kullanır. Aşağıdaki seçeneklerden birini tercih et:

### Seçenek A: OpenAI API (Önerilen)
1. [platform.openai.com](https://platform.openai.com) adresine git
2. Hesap oluştur ve API key al
3. `.env.example` dosyasını `.env` olarak kopyala:
   ```bash
   copy .env.example .env
   ```
4. `.env` dosyasını aç ve `OPENAI_API_KEY` değerini kendi anahtarınla değiştir

### Seçenek B: Google Gemini API
1. [aistudio.google.com](https://aistudio.google.com) adresinden API key al
2. `.env` dosyasında `GOOGLE_API_KEY` satırını aktifleştir ve değeri gir
3. `requirements.txt` dosyasında `google-generativeai` satırındaki yorumu kaldır

### Seçenek C: Yerel Model (Ollama — Ücretsiz, İnternet Gerektirmez)
1. [ollama.com](https://ollama.com) adresinden Ollama'yı indir ve kur
2. Bir model indir: `ollama pull llama3`
3. `.env` dosyasında `OLLAMA_BASE_URL` ve `OLLAMA_MODEL` satırlarını aktifleştir

> 💡 **Hangisini seçmeliyim?**
> - Hızlı başlamak istiyorsan → **OpenAI** (ücretli ama en kolay)
> - Ücretsiz istiyorsan → **Ollama** (bilgisayarın güçlü olmalı, en az 8GB RAM)
> - Google ekosistemini tercih ediyorsan → **Gemini**

---

## 5️⃣ Adım: Projeyi Anla

Koda başlamadan önce proje yapısını anla:

```
src/
├── main.py              # 🚪 Buradan başla! Ana giriş noktası.
│
├── simulation/          # 🛩️ Drone simülasyonu
│   ├── drone.py         #    Drone durumu (konum, irtifa, batarya vb.)
│   ├── environment.py   #    Simülasyon ortamı ve fizik kuralları
│   └── telemetry.py     #    Telemetri okuma sistemi
│
├── agent/               # 🤖 LLM Agent katmanı
│   ├── llm_client.py    #    LLM API ile iletişim
│   ├── command_parser.py #   Kullanıcı komutunu yapılandırılmış göreve çevirme
│   └── prompts.py       #    System/User prompt şablonları
│
├── tools/               # 🔧 Güvenli araç fonksiyonları
│   └── drone_tools.py   #    get_telemetry, takeoff, land, return_to_home
│
├── safety/              # 🛡️ Güvenlik katmanı
│   ├── validator.py     #    Komut doğrulama mantığı
│   └── rules.py         #    Güvenlik kuralları (max irtifa, yasak komutlar vb.)
│
└── logger/              # 📝 Kayıt sistemi
    └── flight_logger.py #    JSON/CSV formatında log tutma
```

---

## 6️⃣ Adım: Geliştirme Sırası (Önerilen)

Projeyi aşağıdaki sırayla geliştirmen önerilir:

### Faz 1 — Simülasyon (LLM olmadan)
1. `src/simulation/drone.py` → Drone durumunu tanımla (x, y, altitude, mode, battery, in_air)
2. `src/simulation/environment.py` → Basit fizik kuralları (kalkınca irtifa artar vb.)
3. `src/simulation/telemetry.py` → Durumu okuyup döndüren fonksiyonlar
4. `src/tools/drone_tools.py` → `get_telemetry()`, `takeoff()`, `land()`, `return_to_home()` fonksiyonlarını yaz

### Faz 2 — Güvenlik Katmanı
5. `src/safety/rules.py` → Güvenlik kurallarını tanımla (max irtifa: 120m, min batarya: %20 vb.)
6. `src/safety/validator.py` → Komutu kurallara göre kontrol eden fonksiyonlar

### Faz 3 — LLM Entegrasyonu
7. `src/agent/prompts.py` → LLM'e gönderilecek system prompt'u yaz
8. `src/agent/llm_client.py` → Seçtiğin LLM API'sine bağlan
9. `src/agent/command_parser.py` → LLM çıktısını yapılandırılmış komuta çevir

### Faz 4 — Birleştirme ve Loglama
10. `src/logger/flight_logger.py` → Log sistemi
11. `src/main.py` → Tüm bileşenleri birleştir, CLI döngüsü yaz
12. `config/settings.py` → Tüm ayarları merkezi bir yere topla

### Faz 5 — Test
13. `tests/` klasöründe en az 12 farklı doğal dil komutu ile test yaz
14. Başarılı, güvensiz, belirsiz ve hatalı komutları dahil et

---

## 7️⃣ Adım: Testleri Çalıştır

```bash
# Tüm testleri çalıştır
pytest tests/ -v

# Belirli bir test dosyasını çalıştır
pytest tests/test_safety.py -v
```

---

## 8️⃣ Adım: Git ile Çalışma

```bash
# Değişiklikleri kaydet
git add .
git commit -m "açıklayıcı bir mesaj"

# Önerilen branch stratejisi
git checkout -b feature/simulation    # Simülasyon geliştirirken
git checkout -b feature/agent         # Agent geliştirirken
git checkout -b feature/safety        # Güvenlik katmanı geliştirirken
```

---

## 📦 Teslim Kontrol Listesi

Projeyi teslim etmeden önce aşağıdakilerin tamamlandığından emin ol:

- [ ] Kaynak kod çalışıyor ve modüler yapıda
- [ ] `README.md` güncel ve kurulum adımları doğru
- [ ] En az 12 farklı doğal dil komutu ile test yapıldı
- [ ] Test logları `logs/` klasöründe mevcut
- [ ] `docs/technical_report.md` yazıldı (mimari, seçimler, güvenlik, test sonuçları)
- [ ] 3-5 dakikalık demo videosu kaydedildi
- [ ] Özgün ek özellik(ler) eklendi ve açıklandı (40 puan!)

---

## ❓ Sık Sorulan Sorular

**S: Simülasyon olarak ne kullanmalıyım?**
Python ile kendi yazdığın basit bir simülasyon yeterli. PX4/Gazebo/AirSim gibi karmaşık ortamlar isteğe bağlı.

**S: LLM motor/PWM gibi düşük seviyeli fonksiyonlara erişmeli mi?**
Hayır! LLM sadece `takeoff`, `land`, `return_to_home`, `go_to` gibi güvenli, yüksek seviyeli fonksiyonları çağırmalı. Son karar güvenlik katmanında verilmeli.

**S: Özgünlük için ne yapabilirim?**
Web arayüzü, sesli komut, batarya yönetimi, çok adımlı görev planlama, LLM karşılaştırması, otomatik senaryo üretici gibi fikirler değerlendirebilirsin. Detaylar için proje dokümanına bak.

**S: Hangi Python sürümünü kullanmalıyım?**
Python 3.10 veya üzeri önerilir. `match-case` gibi modern Python özelliklerinden faydalanabilirsin.

---

> 📌 **İpucu:** Her fazı tamamladıktan sonra commit at. Küçük ve anlamlı commitler, projenin geliştirme sürecini gösterir.
