"""
IHA Pilot Asistanı — Akıllı Batarya Yöneticisi (Özgün Özellik #3)
===================================================================

Bu modül, drone bataryasını sürekli izleyerek proaktif güvenlik
kararları üretir. Basit bir eşik kontrolünden öteye geçerek,
kalan uçuş süresi tahmini ve enerji-temelli komut reddi sağlar.

Özellikler:
    ✦ Gerçek zamanlı batarya durumu izleme
    ✦ Kalan uçuş süresi ve mesafe tahmini
    ✦ Üç seviyeli uyarı sistemi (NORMAL/DÜŞÜK/KRİTİK/ACİL)
    ✦ Enerji bazlı go_to komutu reddi (yeterli batarya yoksa engelle)
    ✦ Otomatik RTH tetikleme (%20 altında)

Enerji Modeli:
    Basitleştirilmiş enerji modeli kullanılmıştır. Gerçek sistemlerde
    bu değer, akım sensörü (shunt resistor) ve voltaj ölçümünden
    hesaplanan mAh bazlı State-of-Charge (SoC) olur.

Demo/Sunum Notu:
    Batarya uyarıları demo sırasında görsel olarak öne çıkar.
    %20 altında otomatik RTH tetiklemesi proaktif güvenliği gösterir.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.simulation.drone import DroneState
from config.settings import settings


# ---------------------------------------------------------------------------
# Batarya Durumu Enum
# ---------------------------------------------------------------------------
class BatteryStatus(Enum):
    """
    Batarya operasyonel durumu.

    NORMAL   : Yeşil — tüm operasyonlara izin
    LOW      : Sarı  — uyarı, kısa görevler önerili
    CRITICAL : Turuncu — yalnızca iniş/RTH
    EMERGENCY: Kırmızı — otomatik acil iniş tetiklenir
    """
    NORMAL = "NORMAL"
    LOW = "LOW"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"

    @property
    def icon(self) -> str:
        icons = {
            "NORMAL": "🟢",
            "LOW": "🟡",
            "CRITICAL": "🟠",
            "EMERGENCY": "🔴",
        }
        return icons.get(self.value, "⚪")

    @property
    def allows_movement(self) -> bool:
        """Hareket komutlarına izin veriyor mu?"""
        return self in (BatteryStatus.NORMAL, BatteryStatus.LOW)


# ---------------------------------------------------------------------------
# Batarya Uyarı Veri Sınıfı
# ---------------------------------------------------------------------------
@dataclass
class BatteryAlert:
    """
    Batarya durumu değerlendirme sonucu.

    Attributes:
        status (BatteryStatus): Mevcut batarya durumu.
        battery_percent (float): Anlık batarya yüzdesi.
        remaining_flight_seconds (float): Tahmini kalan uçuş süresi.
        remaining_cruise_meters (float): Tahmini kalan seyir mesafesi.
        can_return_home (bool): Eve güvenli dönüş mümkün mü?
        rth_battery_cost (float): Eve dönüş için gereken batarya yüzdesi.
        should_auto_rth (bool): Otomatik RTH tetiklenmeli mi?
        message (str): Kullanıcıya gösterilecek uyarı mesajı.
        timestamp (float): Değerlendirme zaman damgası.
    """
    status: BatteryStatus
    battery_percent: float
    remaining_flight_seconds: float
    remaining_cruise_meters: float
    can_return_home: bool
    rth_battery_cost: float
    should_auto_rth: bool
    message: str
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "battery_percent": round(self.battery_percent, 1),
            "remaining_flight_seconds": round(self.remaining_flight_seconds, 1),
            "remaining_flight_minutes": round(self.remaining_flight_seconds / 60, 1),
            "remaining_cruise_meters": round(self.remaining_cruise_meters, 1),
            "can_return_home": self.can_return_home,
            "rth_battery_cost_percent": round(self.rth_battery_cost, 1),
            "should_auto_rth": self.should_auto_rth,
            "message": self.message,
        }

    def format_for_display(self) -> str:
        """Demo video için terminal çıktısı."""
        icon = self.status.icon
        lines = [
            f"  {icon} BATARYA DURUMU: {self.status.value}",
            f"     Seviye          : %{self.battery_percent:.1f}",
            f"     Kalan Uçuş     : {self.remaining_flight_seconds / 60:.1f} dakika",
            f"     Kalan Mesafe    : {self.remaining_cruise_meters:.0f} m",
            f"     Eve Dönüş      : {'✅ Mümkün' if self.can_return_home else '⚠️ SINIRDA'}",
            f"     RTH Batarya    : %{self.rth_battery_cost:.1f}",
        ]
        if self.message:
            lines.append(f"     ⚡ Mesaj: {self.message}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Batarya Yöneticisi
# ---------------------------------------------------------------------------
class BatteryManager:
    """
    Proaktif batarya izleme ve enerji-tabanlı güvenlik yönetimi.

    Bu sınıf, her komut öncesi ve arka planda batarya durumunu
    değerlendirerek kullanıcıyı önceden uyarır.

    Usage::
        manager = BatteryManager()
        alert = manager.evaluate(drone_state)
        if alert.should_auto_rth:
            # RTH başlat
    """

    def evaluate(self, state: DroneState) -> BatteryAlert:
        """
        Mevcut batarya durumunu değerlendir.

        Args:
            state: Mevcut drone durumu.

        Returns:
            BatteryAlert: Detaylı batarya değerlendirme raporu.
        """
        cfg = settings.safety
        sim = settings.simulation
        bat = state.battery

        # Batarya durumu sınıflandırması
        if bat <= cfg.MIN_BATTERY_OPERATION:
            status = BatteryStatus.EMERGENCY
        elif bat <= cfg.MIN_BATTERY_RTH:
            status = BatteryStatus.CRITICAL
        elif bat <= cfg.MIN_BATTERY_WARNING:
            status = BatteryStatus.LOW
        else:
            status = BatteryStatus.NORMAL

        # Kalan uçuş tahmini (hovering bazlı)
        usable = max(0.0, bat - cfg.MIN_BATTERY_RTH)
        drain_rate = sim.BATTERY_DRAIN_HOVER  # %/s
        remaining_seconds = usable / drain_rate if drain_rate > 0 else 0.0
        remaining_meters = remaining_seconds * sim.CRUISE_SPEED

        # Eve dönüş enerji hesabı
        home_dist = state.distance_to_home_2d
        rth_time = home_dist / sim.CRUISE_SPEED if sim.CRUISE_SPEED > 0 else 0
        rth_cost = rth_time * sim.BATTERY_DRAIN_CRUISE
        can_return = (bat - rth_cost) > cfg.MIN_BATTERY_RTH

        # Otomatik RTH tetiklensin mi?
        should_auto_rth = (
            state.in_air
            and bat <= cfg.MIN_BATTERY_RTH
        )

        # Kullanıcı mesajı
        message = self._build_message(status, bat, remaining_seconds, can_return, cfg)

        return BatteryAlert(
            status=status,
            battery_percent=bat,
            remaining_flight_seconds=remaining_seconds,
            remaining_cruise_meters=remaining_meters,
            can_return_home=can_return,
            rth_battery_cost=rth_cost,
            should_auto_rth=should_auto_rth,
            message=message,
        )

    def can_reach_destination(
        self,
        state: DroneState,
        target_x: float,
        target_y: float,
        target_alt: float,
    ) -> tuple[bool, str]:
        """
        Belirtilen hedefe ulaşmak için yeterli enerji var mı?

        Gidiş + geri dönüş enerjisi hesaplanır. Yalnızca gidiş
        için yeterli enerji olsa bile, eve dönemeyecekse reddedilir.

        Args:
            state: Mevcut drone durumu.
            target_x, target_y, target_alt: Hedef koordinatlar.

        Returns:
            tuple[bool, str]: (yeterli mi, gerekçe mesajı)
        """
        sim = settings.simulation
        cfg = settings.safety

        # Hedefe mesafe
        dx = target_x - state.x
        dy = target_y - state.y
        dist_to_target = math.sqrt(dx**2 + dy**2)

        # Hedeften eve mesafe
        dx2 = target_x - state.home_x
        dy2 = target_y - state.home_y
        dist_target_to_home = math.sqrt(dx2**2 + dy2**2)

        total_dist = dist_to_target + dist_target_to_home
        total_time = total_dist / sim.CRUISE_SPEED if sim.CRUISE_SPEED > 0 else 0
        total_cost = total_time * sim.BATTERY_DRAIN_CRUISE

        if state.battery - total_cost < cfg.MIN_BATTERY_RTH:
            return False, (
                f"Hedefe gidiş + eve dönüş için yeterli batarya yok. "
                f"Gereken: %{total_cost:.1f} + %{cfg.MIN_BATTERY_RTH} rezerv. "
                f"Mevcut: %{state.battery:.1f}."
            )
        return True, "Enerji yeterli."

    @staticmethod
    def _build_message(status, bat, remaining_s, can_return, cfg) -> str:
        if status == BatteryStatus.EMERGENCY:
            return f"🔴 ACİL! Batarya %{bat:.0f} — Acil iniş gerekiyor!"
        elif status == BatteryStatus.CRITICAL:
            return (
                f"🟠 KRİTİK: Batarya %{bat:.0f} ≤ %{cfg.MIN_BATTERY_RTH}. "
                f"Yalnızca iniş/eve dönüş! Kalan: {remaining_s/60:.1f} dk."
            )
        elif status == BatteryStatus.LOW:
            return (
                f"🟡 UYARI: Batarya %{bat:.0f}. "
                f"Kalan uçuş: ~{remaining_s/60:.1f} dakika. "
                f"Eve dönüşü planlayın."
            )
        return f"🟢 Batarya %{bat:.0f} — Normal operasyon."
