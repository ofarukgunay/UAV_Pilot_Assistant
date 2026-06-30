"""
IHA Pilot Asistanı — Güvenlik Kuralları Tanım Modülü
=====================================================

Bu modül, İHA sisteminin operasyonel güvenlik kurallarını
yapılandırılmış veri olarak tanımlar.

Güvenlik Mimarisi (Derinlemesine Savunma — Defense in Depth):
    Katman 1: Bu modül — kural tanımları
    Katman 2: SafetyValidator — kural uygulaması
    Katman 3: DroneTools — fonksiyon seviyesi ön doğrulama
    Katman 4: PhysicsEngine — fiziksel kısıtlamalar

Yasal Uyum Referansları:
    - SHGM SHY-İHA-01: Sivil Havacılık Genel Müdürlüğü İHA Yönetmeliği
    - ICAO Annex 2: Rules of the Air (irtifa limitleri)
    - FAA AC 107-2B: Small Unmanned Aircraft Systems (batarya güvenliği)
    - STANAG 4586: UAV Control System Interoperability Standard
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from src.simulation.drone import DroneState
from config.settings import settings


# ---------------------------------------------------------------------------
# Kural İhlal Şiddeti
# ---------------------------------------------------------------------------
class RuleSeverity(Enum):
    """
    Güvenlik kuralı ihlal şiddeti sınıflandırması.

    CAUTION : Dikkat gerektiren durum — işleme devam edilebilir.
    WARNING : Uyarı — operatör bilgilendirilmeli, onay gerekebilir.
    ERROR   : Hata — komut reddedilmeli.
    CRITICAL: Kritik — acil durum prosedürü tetiklenmeli.
    """
    CAUTION = "CAUTION"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Güvenlik Kuralı Veri Sınıfı
# ---------------------------------------------------------------------------
@dataclass
class SafetyRule:
    """
    Tek bir güvenlik kuralını tanımlayan yapı.

    Attributes:
        rule_id (str): Benzersiz kural kimliği (örn: 'SR-ALT-001').
        name (str): Kısa kural adı.
        description (str): Ayrıntılı açıklama ve gerekçe.
        severity (RuleSeverity): İhlal şiddeti.
        applies_to (list[str]): Bu kuralın uygulandığı eylemler.
                                Boş liste = tüm eylemlere uygulanır.
        check (Callable): (action, params, state) → (passed: bool, reason: str)
        suggestion (str): İhlal durumunda kullanıcıya önerilen eylem.
        legal_ref (str): Yasal/standart referans.
    """
    rule_id: str
    name: str
    description: str
    severity: RuleSeverity
    applies_to: list[str]
    check: Callable[[str, dict, DroneState], tuple[bool, str]]
    suggestion: str = ""
    legal_ref: str = ""


# ---------------------------------------------------------------------------
# Kural Fabrikası — Tüm Aktif Güvenlik Kuralları
# ---------------------------------------------------------------------------
def build_safety_rules() -> list[SafetyRule]:
    """
    Sistemin aktif güvenlik kuralı listesini oluştur ve döndür.

    Yeni kural eklemek için bu fonksiyona SafetyRule nesnesi ekleyin.
    Kural test edilebilirlik için lambda/fonksiyon tabanlı tasarlanmıştır.

    Returns:
        list[SafetyRule]: Öncelik sırasına göre sıralanmış kurallar.
    """
    cfg = settings.safety

    rules: list[SafetyRule] = [

        # ── SR-BAT-001: Acil Batarya Seviyesi ──────────────────────────────
        SafetyRule(
            rule_id="SR-BAT-001",
            name="Acil Batarya Seviyesi",
            description=(
                "Batarya seviyesi kritik eşiğin altındaysa hiçbir hareket "
                "komutu (kalkış, navigasyon) uygulanamaz. "
                "FAA AC 107-2B Section 6.3.1: Minimum güç rezervi."
            ),
            severity=RuleSeverity.CRITICAL,
            applies_to=["takeoff", "go_to"],
            check=lambda action, params, state: (
                state.battery > cfg.MIN_BATTERY_OPERATION,
                f"Batarya seviyesi %{state.battery:.1f} — minimum operasyon "
                f"eşiği %{cfg.MIN_BATTERY_OPERATION} altında.",
            ),
            suggestion=f"Bataryayı şarj edin (minimum %{cfg.MIN_BATTERY_OPERATION} gerekli).",
            legal_ref="FAA AC 107-2B §6.3.1",
        ),

        # ── SR-BAT-002: RTH Batarya Uyarısı ────────────────────────────────
        SafetyRule(
            rule_id="SR-BAT-002",
            name="Eve Dönüş Batarya Eşiği",
            description=(
                "Batarya RTH eşiğinin altına düştüğünde yalnızca "
                "'land' ve 'return_to_home' komutlarına izin verilir. "
                "Diğer tüm hareket komutları engellenir."
            ),
            severity=RuleSeverity.ERROR,
            applies_to=["go_to", "takeoff"],
            check=lambda action, params, state: (
                state.battery > cfg.MIN_BATTERY_RTH or not state.in_air,
                f"Batarya RTH eşiğinin altında (%{state.battery:.1f} ≤ %{cfg.MIN_BATTERY_RTH}). "
                f"Yalnızca iniş/eve dönüş komutlarına izin verilir.",
            ),
            suggestion="'Eve dön' veya 'İniş yap' komutunu kullanın.",
            legal_ref="SHGM SHY-İHA-01 Madde 5.4.2",
        ),

        # ── SR-ALT-001: Maksimum İrtifa ─────────────────────────────────────
        SafetyRule(
            rule_id="SR-ALT-001",
            name="Maksimum Operasyonel İrtifa",
            description=(
                f"İHA'nın hedef irtifası {cfg.MAX_ALTITUDE}m AGL'yi aşamaz. "
                f"SHGM SHY-İHA-01 Madde 5.1.3: Görsel hat içi operasyonlarda "
                f"maksimum irtifa 120 metre."
            ),
            severity=RuleSeverity.ERROR,
            applies_to=["takeoff", "go_to"],
            check=lambda action, params, state: (
                params.get("target_altitude", params.get("altitude", 0)) <= cfg.MAX_ALTITUDE,
                f"Hedef irtifa {params.get('target_altitude', params.get('altitude', 0))}m "
                f"> maksimum izinli {cfg.MAX_ALTITUDE}m AGL.",
            ),
            suggestion=f"İrtifayı {cfg.MAX_ALTITUDE}m veya altına düşürün.",
            legal_ref="SHGM SHY-İHA-01 §5.1.3 / ICAO Annex 2",
        ),

        # ── SR-ALT-002: Minimum Kalkış İrtifası ────────────────────────────
        SafetyRule(
            rule_id="SR-ALT-002",
            name="Minimum Kalkış İrtifası",
            description=(
                f"Kalkış hedef irtifası en az {cfg.MIN_TAKEOFF_ALTITUDE}m olmalıdır. "
                f"Sıfır veya negatif değer fiziksel anlamsızdır."
            ),
            severity=RuleSeverity.ERROR,
            applies_to=["takeoff"],
            check=lambda action, params, state: (
                params.get("target_altitude", 0) >= cfg.MIN_TAKEOFF_ALTITUDE,
                f"Kalkış irtifası {params.get('target_altitude', 0)}m < "
                f"minimum {cfg.MIN_TAKEOFF_ALTITUDE}m.",
            ),
            suggestion=f"En az {cfg.MIN_TAKEOFF_ALTITUDE}m irtifa belirtin.",
            legal_ref="Operasyonel güvenlik standardı",
        ),

        # ── SR-ALT-003: Tek Komutla Maksimum Kalkış ─────────────────────────
        SafetyRule(
            rule_id="SR-ALT-003",
            name="Tek Komutla Maksimum Kalkış İrtifası",
            description=(
                f"Tek bir kalkış komutunda hedeflenen maksimum irtifa "
                f"{cfg.MAX_TAKEOFF_ALTITUDE}m ile sınırlandırılmıştır. "
                f"Daha yüksek irtifa için aşamalı kalkış gereklidir."
            ),
            severity=RuleSeverity.WARNING,
            applies_to=["takeoff"],
            check=lambda action, params, state: (
                params.get("target_altitude", 0) <= cfg.MAX_TAKEOFF_ALTITUDE,
                f"Tek komutla kalkış irtifası {params.get('target_altitude', 0)}m "
                f"> önerilen {cfg.MAX_TAKEOFF_ALTITUDE}m.",
            ),
            suggestion=f"İrtifayı {cfg.MAX_TAKEOFF_ALTITUDE}m veya altında belirtin.",
            legal_ref="Operasyonel prosedür",
        ),

        # ── SR-FLT-001: Havada İken Tekrar Kalkış ───────────────────────────
        SafetyRule(
            rule_id="SR-FLT-001",
            name="Uçuş Durumu Çakışması — Kalkış",
            description=(
                "Araç havadayken kalkış komutu verilemez. "
                "Bu durum, uçuş modu çakışmasına (mode confusion) yol açar."
            ),
            severity=RuleSeverity.ERROR,
            applies_to=["takeoff"],
            check=lambda action, params, state: (
                not state.in_air,
                f"Araç zaten havada (İrtifa: {state.altitude:.1f}m, Mod: {state.mode.value}). "
                f"Kalkış komutu geçersiz.",
            ),
            suggestion="Önce iniş yapın, ardından tekrar kalkış emri verin.",
            legal_ref="Operasyonel prosedür",
        ),

        # ── SR-FLT-002: Yerdeyken İniş/RTH ─────────────────────────────────
        SafetyRule(
            rule_id="SR-FLT-002",
            name="Uçuş Durumu Çakışması — İniş/RTH",
            description=(
                "Araç yerdeyken iniş veya RTH komutu verilemez."
            ),
            severity=RuleSeverity.ERROR,
            applies_to=["land", "return_to_home"],
            check=lambda action, params, state: (
                state.in_air,
                f"Araç zaten yerde (Mod: {state.mode.value}). "
                f"İniş/RTH komutu geçersiz.",
            ),
            suggestion="Önce kalkış yapın.",
            legal_ref="Operasyonel prosedür",
        ),

        # ── SR-GEO-001: Geofence İhlali ─────────────────────────────────────
        SafetyRule(
            rule_id="SR-GEO-001",
            name="Coğrafi Sınır (Geofence) İhlali",
            description=(
                f"Araç, başlangıç noktasından {cfg.GEOFENCE_RADIUS}m yarıçaplı "
                f"silindir geofence dışına çıkamaz."
            ),
            severity=RuleSeverity.ERROR,
            applies_to=["go_to"],
            check=lambda action, params, state: (
                __import__("math").sqrt(
                    params.get("x", 0) ** 2 + params.get("y", 0) ** 2
                ) <= cfg.GEOFENCE_RADIUS,
                f"Hedef konum ({params.get('x', 0):.0f}m, {params.get('y', 0):.0f}m) "
                f"geofence dışında. "
                f"Başlangıca mesafe: "
                f"{__import__('math').sqrt(params.get('x',0)**2+params.get('y',0)**2):.0f}m "
                f"> {cfg.GEOFENCE_RADIUS}m.",
            ),
            suggestion=f"Başlangıç noktasına {cfg.GEOFENCE_RADIUS}m içinde kalın.",
            legal_ref="SHGM SHY-İHA-01 operasyonel sınırlar",
        ),

        # ── SR-GEO-002: go_to Hedef İrtifası ────────────────────────────────
        SafetyRule(
            rule_id="SR-GEO-002",
            name="go_to Hedef İrtifası Limiti",
            description=(
                "go_to komutundaki hedef irtifa maksimum irtifa sınırını aşamaz."
            ),
            severity=RuleSeverity.ERROR,
            applies_to=["go_to"],
            check=lambda action, params, state: (
                params.get("altitude", 0) <= cfg.MAX_ALTITUDE,
                f"Hedef irtifa {params.get('altitude', 0)}m > maksimum {cfg.MAX_ALTITUDE}m.",
            ),
            suggestion=f"İrtifayı {cfg.MAX_ALTITUDE}m veya altına düşürün.",
            legal_ref="SHGM SHY-İHA-01 §5.1.3",
        ),

        # ── SR-GEO-003: go_to Minimum İrtifa ────────────────────────────────
        SafetyRule(
            rule_id="SR-GEO-003",
            name="go_to Minimum İrtifa",
            description="go_to hedef irtifası negatif olamaz.",
            severity=RuleSeverity.ERROR,
            applies_to=["go_to"],
            check=lambda action, params, state: (
                params.get("altitude", 0) >= 0,
                f"Hedef irtifa {params.get('altitude', 0)}m < 0. Geçersiz değer.",
            ),
            suggestion="Pozitif bir irtifa değeri girin.",
            legal_ref="Fiziksel kısıt",
        ),
    ]

    return rules


# Modül düzeyinde kural listesi — import edilebilir
SAFETY_RULES: list[SafetyRule] = build_safety_rules()
