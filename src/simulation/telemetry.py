"""
IHA Pilot Asistanı — Telemetri Okuma Sistemi
=============================================

Bu modül, drone'un anlık durumunu okunabilir formatlara çevirerek
hem insan kullanıcılara hem de LLM agent'ına sunar.

Gerçek Sistem Karşılığı:
    Gerçek bir İHA sisteminde bu modül, MAVLink telemetri stream'ini
    (HEARTBEAT, GLOBAL_POSITION_INT, BATTERY_STATUS, SYS_STATUS
    mesajları) dinleyip işler. Simülasyon ortamında ise DroneState
    veri yapısından doğrudan okur.

    MAVLink Referansı: https://mavlink.io/en/messages/common.html
"""

from __future__ import annotations

from typing import Dict, Any

from src.simulation.drone import DroneState, FlightMode
from config.settings import settings


class TelemetryReader:
    """
    Drone telemetri okuma ve formatlama sınıfı.

    Bu sınıf durum bilgisini:
        - İnsan okunabilir metin formatında (Türkçe)
        - LLM bağlamı için yapılandırılmış sözlük olarak
        - Web dashboard için JSON formatında

    sunar.
    """

    # Mod açıklamaları — Türkçe kullanıcı arayüzü için
    MODE_DESCRIPTIONS: Dict[str, str] = {
        FlightMode.IDLE.value: "Yerde bekleme (motorlar kapalı)",
        FlightMode.ARMED.value: "Kalkışa hazır (motorlar devrede)",
        FlightMode.TAKEOFF.value: "Kalkış manevrası aktif",
        FlightMode.HOVERING.value: "Sabit irtifada bekleme",
        FlightMode.NAVIGATING.value: "Hedefe aktif navigasyon",
        FlightMode.LANDING.value: "İniş manevrası aktif",
        FlightMode.RETURN_TO_HOME.value: "Otomatik eve dönüş",
        FlightMode.EMERGENCY.value: "⚠️ ACİL DURUM — öncelikli iniş",
    }

    def __init__(self, state: DroneState) -> None:
        """
        Args:
            state: Anlık drone durum nesnesi.
        """
        self._state = state

    def update(self, state: DroneState) -> None:
        """Telemetri okuyucunun referans aldığı state'i güncelle."""
        self._state = state

    # -----------------------------------------------------------------------
    # Ham Veri Erişimi
    # -----------------------------------------------------------------------

    def get_raw(self) -> Dict[str, Any]:
        """
        Ham telemetri verisi.

        Returns:
            dict: DroneState'in tam JSON serileştirmesi.
        """
        return self._state.to_dict()

    # -----------------------------------------------------------------------
    # İnsan Okunabilir Format
    # -----------------------------------------------------------------------

    def get_human_readable(self) -> str:
        """
        Drone durumunu Türkçe, okunabilir metin olarak döndür.

        LLM agent'ının sistem bağlamına ve kullanıcı yanıtlarına
        eklenir.

        Returns:
            str: Çok satırlı durum raporu.
        """
        s = self._state
        safety_cfg = settings.safety

        # Batarya uyarı ikon
        bat_icon = "🟢" if s.battery >= 50 else ("🟡" if s.battery >= 30 else "🔴")
        mode_desc = self.MODE_DESCRIPTIONS.get(s.mode.value, s.mode.value)

        lines = [
            "═══════════════════════════════════════",
            "       📡 CANLI TELEMETRİ RAPORU        ",
            "═══════════════════════════════════════",
            f"  MOD        : {s.mode.value} — {mode_desc}",
            f"  KONUM      : X={s.x:+.1f}m (D), Y={s.y:+.1f}m (K)",
            f"  İRTİFA     : {s.altitude:.1f} m AGL",
            f"  HIZ        : {s.speed:.1f} m/s (yatay)",
            f"  DİKEY HIZ  : {s.vertical_speed:+.1f} m/s",
            f"  YÖN        : {s.heading:.0f}° ({self._heading_label(s.heading)})",
            f"  BATARYA    : {bat_icon} %{s.battery:.1f} — {s.battery_level_label}",
            f"  HAVADA     : {'Evet ✈' if s.in_air else 'Hayır 🛬'}",
            f"  EVE UZAKLIK: {s.distance_to_home_2d:.1f} m",
            f"  UÇUŞ SÜRESİ: {self._format_duration(s.flight_duration)}",
        ]

        if s.mission_active:
            lines.append(
                f"  GÖREV      : Aktif — {s.mission_name} (Adım {s.mission_step + 1})"
            )

        # Güvenlik uyarıları
        warnings = self._get_warnings()
        if warnings:
            lines.append("  ─────────────────────────────────────")
            for w in warnings:
                lines.append(f"  {w}")

        lines.append("═══════════════════════════════════════")
        return "\n".join(lines)

    def get_concise(self) -> str:
        """
        Özet tek satır durum (komut satırı prompt için).

        Returns:
            str: Örn. '[HOVERING | Alt:50m | Bat:%75 | 0.0m/s]'
        """
        s = self._state
        return (
            f"[{s.mode.value} | "
            f"Alt:{s.altitude:.0f}m | "
            f"Bat:%{s.battery:.0f} | "
            f"Hız:{s.speed:.1f}m/s]"
        )

    def get_llm_context(self) -> str:
        """
        LLM'e verilecek kısa bağlam metni.

        System prompt'a eklenerek agent'ın mevcut durum hakkında
        bilinçli kararlar vermesi sağlanır.

        Returns:
            str: Yapılandırılmış bağlam metni.
        """
        s = self._state
        return (
            f"DRONE_STATE: mode={s.mode.value}, "
            f"altitude={s.altitude:.1f}m, "
            f"battery={s.battery:.1f}%, "
            f"in_air={s.in_air}, "
            f"position=({s.x:.1f},{s.y:.1f}), "
            f"speed={s.speed:.1f}m/s, "
            f"distance_to_home={s.distance_to_home_2d:.1f}m"
        )

    # -----------------------------------------------------------------------
    # Batarya Tahmini
    # -----------------------------------------------------------------------

    def estimate_flight_remaining(self) -> Dict[str, Any]:
        """
        Mevcut batarya ile kalan uçuş süresi ve mesafe tahmini.

        Basitleştirilmiş enerji modeli:
            Kalan enerji = (battery% - MIN_RTH%) / DRAIN_RATE_HOVER
            Bu değer, maximum hovering süresini verir.
            Seyir mesafesi = süre × CRUISE_SPEED

        Returns:
            dict: remaining_seconds, remaining_distance_m, can_return_home
        """
        s = self._state
        safety_cfg = settings.safety
        sim_cfg = settings.simulation

        usable_battery = max(0.0, s.battery - safety_cfg.MIN_BATTERY_RTH)
        drain_rate = sim_cfg.BATTERY_DRAIN_HOVER  # %/saniye
        remaining_seconds = usable_battery / drain_rate if drain_rate > 0 else 0.0
        remaining_distance = remaining_seconds * sim_cfg.CRUISE_SPEED

        # Eve dönüş için yeterli enerji var mı?
        rth_distance = s.distance_to_home_2d
        rth_time = rth_distance / sim_cfg.CRUISE_SPEED if sim_cfg.CRUISE_SPEED > 0 else 0
        rth_battery_needed = rth_time * sim_cfg.BATTERY_DRAIN_CRUISE
        can_return = s.battery - rth_battery_needed > safety_cfg.MIN_BATTERY_RTH

        return {
            "remaining_flight_seconds": round(remaining_seconds, 1),
            "remaining_flight_minutes": round(remaining_seconds / 60, 1),
            "remaining_cruise_distance_m": round(remaining_distance, 1),
            "can_safely_return_home": can_return,
            "rth_battery_cost_percent": round(rth_battery_needed, 1),
        }

    # -----------------------------------------------------------------------
    # Yardımcı Metodlar
    # -----------------------------------------------------------------------

    def _heading_label(self, heading: float) -> str:
        """Derece cinsinden yönü pusula yönüne çevir."""
        directions = ["K", "KD", "D", "GD", "G", "GB", "B", "KB"]
        idx = round(heading / 45) % 8
        return directions[idx]

    def _format_duration(self, seconds: float) -> str:
        """Saniyeyi MM:SS formatına çevir."""
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"

    def _get_warnings(self) -> list:
        """Aktif güvenlik uyarılarını listele."""
        warnings = []
        s = self._state
        safety_cfg = settings.safety

        if s.battery <= safety_cfg.MIN_BATTERY_RTH:
            warnings.append("🔴 UYARI: Acil batarya seviyesi — Otomatik RTH başlatılıyor!")
        elif s.battery <= safety_cfg.MIN_BATTERY_WARNING:
            warnings.append("🟡 UYARI: Batarya düşük — Eve dönüşü planlayın.")

        if s.altitude >= safety_cfg.MAX_ALTITUDE * 0.9:
            warnings.append(
                f"🟡 UYARI: Maksimum irtifaya yakın ({s.altitude:.0f}m / {safety_cfg.MAX_ALTITUDE}m)"
            )
        if s.distance_to_home_2d >= safety_cfg.GEOFENCE_RADIUS * 0.9:
            warnings.append(
                f"🟡 UYARI: Geofence sınırına yakın ({s.distance_to_home_2d:.0f}m / {safety_cfg.GEOFENCE_RADIUS}m)"
            )
        return warnings
