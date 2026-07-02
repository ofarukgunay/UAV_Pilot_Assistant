"""
IHA Pilot Asistanı — Merkezi Yapılandırma Modülü
=================================================

Bu modül, sistemin tüm yapılandırma parametrelerini merkezi
olarak yönetir. Güvenlik limitleri SHGM SHY-İHA-01 yönetmeliği
ve ICAO Annex 2 standartları referans alınarak belirlenmiştir.

Birim Sözlüğü:
    İrtifa  : metre (AGL — Above Ground Level / Yer Üstü Yüksekliği)
    Hız     : m/s (metre/saniye)
    Mesafe  : metre
    Batarya : % (0–100 arası yüzde)
    Süre    : saniye
    Açı     : derece (0 = Kuzey, saat yönünde artar)

Kullanım:
    from config.settings import Settings
    cfg = Settings()
    print(cfg.MAX_ALTITUDE)  # 120
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Proje kök dizini
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# .env dosyasını yükle (varsa)
load_dotenv(PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# Yol Sabitleri
# ---------------------------------------------------------------------------
LOGS_DIR = PROJECT_ROOT / "logs"
DOCS_DIR = PROJECT_ROOT / "docs"
TESTS_DIR = PROJECT_ROOT / "tests"

# Klasörlerin var olduğundan emin ol
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Simülasyon Parametreleri
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SimulationConfig:
    """
    Drone fizik simülasyonu yapılandırma parametreleri.

    Notlar:
        PHYSICS_TICK_HZ : Fizik motorunun güncellenme frekansı (Hz).
                          Gerçek sistemlerde bu değer genellikle 400 Hz'dir
                          (Pixhawk FCU iç döngüsü). Simülasyon için 10 Hz yeterlidir.
        TAKEOFF_SPEED   : Kalkış dikey hızı (m/s). DJI M300 RTK referans: ~5 m/s.
        CRUISE_SPEED    : Yatay seyir hızı (m/s). SHY-İHA-01 Sınıf-1 için tipik değer.
    """
    PHYSICS_TICK_HZ: float = 10.0          # Hz
    TAKEOFF_SPEED: float = 2.5             # m/s dikey
    LANDING_SPEED: float = 1.5             # m/s dikey
    CRUISE_SPEED: float = 8.0              # m/s yatay
    ACCELERATION: float = 2.0             # m/s²
    BATTERY_DRAIN_IDLE: float = 0.02       # %/saniye (yerde)
    BATTERY_DRAIN_HOVER: float = 0.08      # %/saniye (hovering)
    BATTERY_DRAIN_CRUISE: float = 0.12     # %/saniye (seyir)
    BATTERY_DRAIN_TAKEOFF: float = 0.15    # %/saniye (kalkış)
    HOME_LATITUDE: float = 39.9334         # Ankara — simülasyon referans koordinatı
    HOME_LONGITUDE: float = 32.8597


# ---------------------------------------------------------------------------
# Güvenlik Limitleri
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SafetyConfig:
    """
    Güvenlik katmanı sınır değerleri.

    Yasal Referanslar:
        MAX_ALTITUDE     : SHGM SHY-İHA-01 Madde 5.1.3 — Görsel hattı dahilinde
                           maksimum operasyonel irtifa 120 metre AGL.
        MIN_BATTERY_RTH  : Otomatik eve dönüş için acil batarya eşiği.
                           FAA AC 107-2 'Risk-Based Approach' tavsiye değeri.
        GEOFENCE_RADIUS  : Başlangıç noktasından maksimum yatay mesafe.
    """
    MAX_ALTITUDE: float = 120.0            # metre AGL (SHGM SHY-İHA-01)
    MIN_ALTITUDE_FLIGHT: float = 0.5       # metre (gömülü engel eşiği)
    MAX_SPEED: float = 15.0               # m/s (operasyonel limit)
    MAX_TAKEOFF_ALTITUDE: float = 100.0   # metre (tek komutla maksimum kalkış)
    MIN_TAKEOFF_ALTITUDE: float = 1.0     # metre (minimum anlamlı kalkış)
    MIN_BATTERY_RTH: float = 20.0         # % (acil otomatik RTH eşiği)
    MIN_BATTERY_WARNING: float = 30.0     # % (sarı uyarı eşiği)
    MIN_BATTERY_OPERATION: float = 15.0   # % (bu altında hiçbir hareket komutu)
    GEOFENCE_RADIUS: float = 500.0        # metre (başlangıç noktasından)
    CRITICAL_CONFIRM_ACTIONS: frozenset = field(
        default_factory=lambda: frozenset({"emergency_land", "motor_stop"})
    )


# ---------------------------------------------------------------------------
# LLM Yapılandırması
# ---------------------------------------------------------------------------
@dataclass
class LLMConfig:
    """
    Büyük Dil Modeli (LLM) bağlantı ve çalışma parametreleri.

    Desteklenen Sağlayıcılar:
        ollama  : Yerel çalışan model (varsayılan, ücretsiz)
        openai  : OpenAI API (GPT-4o, ücretli)
        gemini  : Google Gemini API (ücretsiz kota mevcut)
    """
    PROVIDER: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "ollama"))
    # Ollama
    OLLAMA_BASE_URL: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    OLLAMA_MODEL: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3")
    )
    OLLAMA_TIMEOUT: int = 60               # saniye
    # OpenAI
    OPENAI_API_KEY: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    OPENAI_MODEL: str = "gpt-4o"
    # Gemini
    GOOGLE_API_KEY: str = field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY", "")
    )
    # Genel
    MAX_RETRIES: int = 3
    TEMPERATURE: float = 0.1              # Düşük → tutarlı, belirleyici çıktı
    MAX_TOKENS: int = 1024


# ---------------------------------------------------------------------------
# Web Dashboard Yapılandırması
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WebConfig:
    """Flask tabanlı web dashboard yapılandırması."""
    HOST: str = "127.0.0.1"
    PORT: int = 5000
    DEBUG: bool = False
    SECRET_KEY: str = field(
        default_factory=lambda: os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
    )
    TELEMETRY_PUSH_INTERVAL: float = 1.0  # saniye (WebSocket güncelleme aralığı)


# ---------------------------------------------------------------------------
# Loglama Yapılandırması
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LogConfig:
    """
    Uçuş kayıt sistemi yapılandırması.

    Log Formatları:
        JSON : Makine tarafından okunabilir, analiz için
        CSV  : Tablo araçları (Excel, pandas) için
        HTML : İnsan tarafından okunabilir test raporu
    """
    LOG_DIR: Path = LOGS_DIR
    JSON_LOG_FILE: str = "flight_log.json"
    CSV_LOG_FILE: str = "flight_log.csv"
    HTML_REPORT_FILE: str = "test_report.html"
    LOG_LEVEL: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    MAX_LOG_ENTRIES: int = 10_000


# ---------------------------------------------------------------------------
# Ana Yapılandırma Nesnesi
# ---------------------------------------------------------------------------
@dataclass
class Settings:
    """
    Sistem geneli yapılandırma ana nesnesi.

    Örnek kullanım::

        from config.settings import Settings
        cfg = Settings()
        if drone.altitude > cfg.safety.MAX_ALTITUDE:
            raise SafetyViolation(...)
    """
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    web: WebConfig = field(default_factory=WebConfig)
    log: LogConfig = field(default_factory=LogConfig)

    # Kısayollar (sık kullanılan değerlere hızlı erişim)
    @property
    def MAX_ALTITUDE(self) -> float:
        return self.safety.MAX_ALTITUDE

    @property
    def MIN_BATTERY_RTH(self) -> float:
        return self.safety.MIN_BATTERY_RTH

    @property
    def OLLAMA_MODEL(self) -> str:
        return self.llm.OLLAMA_MODEL


# Modül düzeyinde singleton örnek — import edilebilir
settings = Settings()
