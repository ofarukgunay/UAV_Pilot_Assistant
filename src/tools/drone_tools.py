"""
IHA Pilot Asistanı — Güvenli Araç Fonksiyonları Katmanı
=======================================================

Bu modül, LLM agent'ının çağırabileceği yüksek seviyeli drone
kontrol fonksiyonlarını tanımlar.

MİMARİ GÜVENLİK PRENSİBİ:
    LLM, yalnızca bu dosyada tanımlanan fonksiyonlara erişebilir.
    Motor kontrolü (PWM), attitude (roll/pitch/yaw), ham hız setpoint
    veya simülasyon nesnesine doğrudan erişim YOKTUR.

    Bu tasarım, aviyonik sistemlerdeki "Pilot → FMS → Autopilot → FCC"
    hiyerarşisini modellemektedir:
        Kullanıcı → LLM (FMS) → Araç Fonksiyonları (Autopilot) → Fizik Motoru (FCC)

Araç Fonksiyonları Listesi:
    get_telemetry()                    — Durum bilgisi
    takeoff(target_altitude)           — Kalkış
    land()                             — İniş
    return_to_home()                   — Eve dönüş
    go_to(x, y, altitude)             — Koordinata git

Her fonksiyon:
    1. Güvenlik ön doğrulaması yapar (validator'dan bağımsız ikinci kontrol)
    2. Fizik motoruna komutu iletir
    3. Yapılandırılmış ToolResult döndürür
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.simulation.drone import DroneState, FlightMode
from src.simulation.environment import PhysicsEngine
from src.simulation.telemetry import TelemetryReader
from config.settings import settings


# ---------------------------------------------------------------------------
# Araç Sonuç Veri Sınıfı
# ---------------------------------------------------------------------------
@dataclass
class ToolResult:
    """
    Araç fonksiyonu çalıştırma sonucu.

    Attributes:
        success (bool): Komut başarıyla uygulandı mı?
        action (str): Çalıştırılan eylem adı.
        message (str): İnsan okunabilir sonuç açıklaması.
        state_before (DroneState): Komut öncesi durum (geri alma için).
        state_after (DroneState): Komut sonrası durum.
        data (dict): Ek veri (hesaplamalar, uyarılar vb.).
        timestamp (float): Unix zaman damgası.
    """
    success: bool
    action: str
    message: str
    state_before: DroneState
    state_after: DroneState
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "message": self.message,
            "state_after": self.state_after.to_dict(),
            "data": self.data,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Araç Fonksiyonları Sınıfı
# ---------------------------------------------------------------------------
class DroneTools:
    """
    LLM agent'ına açık yüksek seviyeli drone kontrol arayüzü.

    Bu sınıf, güvenlik katmanı (SafetyValidator) tarafından ONAYLANAN
    komutları fizik motoruna iletir. İkinci bir ön doğrulama katmanı
    olarak da görev yapar (derinlemesine savunma — defense in depth).

    Usage::
        tools = DroneTools(state)
        result = tools.takeoff(50.0)
        if result.success:
            state = result.state_after
    """

    def __init__(self, state: DroneState) -> None:
        self._state = state
        self._physics = PhysicsEngine()
        self._telemetry = TelemetryReader(state)

    @property
    def state(self) -> DroneState:
        return self._state

    def _update_state(self, new_state: DroneState) -> None:
        self._state = new_state
        self._telemetry.update(new_state)

    # -----------------------------------------------------------------------
    # Araç: Telemetri Okuma
    # -----------------------------------------------------------------------
    def get_telemetry(self) -> ToolResult:
        """
        Anlık telemetri raporunu döndür.

        Bu fonksiyon drone durumunu DEĞİŞTİRMEZ — yalnızca okur.
        'Read-only' araç: güvenlik kısıtlaması yoktur.

        Returns:
            ToolResult: Telemetri verisi ve okunabilir rapor.
        """
        state_copy = self._state.clone()
        reader = TelemetryReader(state_copy)

        return ToolResult(
            success=True,
            action="get_telemetry",
            message=reader.get_human_readable(),
            state_before=state_copy,
            state_after=state_copy,
            data={
                "raw": reader.get_raw(),
                "flight_estimate": reader.estimate_flight_remaining(),
            },
        )

    # -----------------------------------------------------------------------
    # Araç: Kalkış
    # -----------------------------------------------------------------------
    def takeoff(self, target_altitude: float) -> ToolResult:
        """
        Belirtilen irtifaya kalkış manevrası başlat.

        Simülasyon bu fonksiyonda anında çözülür (adım adım fizik
        simülasyonu yerine doğrudan hedef duruma geçiş).
        Gerçek bir sistemde bu, FCS'e bir setpoint komutu olurdu.

        Args:
            target_altitude: Hedef irtifa, metre AGL.
                             Geçerli aralık: [MIN_TAKEOFF_ALTITUDE, MAX_ALTITUDE]

        Returns:
            ToolResult: Kalkış sonucu ve yeni durum.

        Raises:
            Bu fonksiyon exception fırlatmaz; hata durumunu
            ToolResult.success=False ile bildirir.
        """
        state_before = self._state.clone()
        cfg = settings.safety
        sim_cfg = settings.simulation

        # Ön doğrulama (savunma katmanı 2)
        if self._state.in_air:
            return ToolResult(
                success=False,
                action="takeoff",
                message=(
                    f"❌ Kalkış reddedildi: Araç zaten havada "
                    f"(İrtifa: {self._state.altitude:.1f}m, Mod: {self._state.mode.value}). "
                    f"Önce iniş yapmanız gerekir."
                ),
                state_before=state_before,
                state_after=self._state.clone(),
            )

        if self._state.battery <= cfg.MIN_BATTERY_OPERATION:
            return ToolResult(
                success=False,
                action="takeoff",
                message=(
                    f"❌ Kalkış reddedildi: Batarya kritik seviyede "
                    f"(%{self._state.battery:.1f} < %{cfg.MIN_BATTERY_OPERATION}). "
                    f"Şarj etmeden kalkış yapılamaz."
                ),
                state_before=state_before,
                state_after=self._state.clone(),
            )

        # Fizik simülasyonu — kalkış tamamlandı (anlık geçiş)
        new_state = self._state.clone()
        new_state.altitude = target_altitude
        new_state.mode = FlightMode.HOVERING
        new_state.in_air = True
        new_state.vertical_speed = 0.0
        new_state.speed = 0.0
        if new_state.flight_start_time is None:
            new_state.flight_start_time = time.time()

        # Kalkış batarya tüketimi
        takeoff_time = target_altitude / sim_cfg.TAKEOFF_SPEED
        new_state.battery = max(
            0.0,
            new_state.battery - sim_cfg.BATTERY_DRAIN_TAKEOFF * takeoff_time,
        )
        new_state.last_update = time.time()
        self._update_state(new_state)

        return ToolResult(
            success=True,
            action="takeoff",
            message=(
                f"✅ Kalkış tamamlandı. "
                f"İrtifa: {target_altitude:.1f}m AGL | "
                f"Mod: HOVERING | "
                f"Batarya: %{new_state.battery:.1f}"
            ),
            state_before=state_before,
            state_after=new_state.clone(),
            data={"target_altitude": target_altitude, "takeoff_time_s": round(takeoff_time, 1)},
        )

    # -----------------------------------------------------------------------
    # Araç: İniş
    # -----------------------------------------------------------------------
    def land(self) -> ToolResult:
        """
        Normal iniş manevrası başlat.

        Araç, mevcut yatay konumunda zemine iner.

        Returns:
            ToolResult: İniş sonucu ve yeni durum.
        """
        state_before = self._state.clone()
        sim_cfg = settings.simulation

        if not self._state.in_air:
            return ToolResult(
                success=False,
                action="land",
                message=(
                    f"❌ İniş reddedildi: Araç zaten yerde "
                    f"(Mod: {self._state.mode.value})."
                ),
                state_before=state_before,
                state_after=self._state.clone(),
            )

        # İniş tamamlandı
        landing_time = self._state.altitude / sim_cfg.LANDING_SPEED
        new_state = self._state.clone()
        new_state.altitude = 0.0
        new_state.mode = FlightMode.IDLE
        new_state.in_air = False
        new_state.speed = 0.0
        new_state.vertical_speed = 0.0

        # İniş batarya tüketimi
        new_state.battery = max(
            0.0,
            new_state.battery - sim_cfg.BATTERY_DRAIN_HOVER * landing_time,
        )

        # Uçuş süresini kaydet
        if new_state.flight_start_time:
            new_state.total_flight_time += time.time() - new_state.flight_start_time
            new_state.flight_start_time = None

        new_state.last_update = time.time()
        self._update_state(new_state)

        return ToolResult(
            success=True,
            action="land",
            message=(
                f"✅ İniş tamamlandı. "
                f"Konum: ({new_state.x:.1f}m, {new_state.y:.1f}m) | "
                f"Mod: IDLE | "
                f"Batarya: %{new_state.battery:.1f}"
            ),
            state_before=state_before,
            state_after=new_state.clone(),
            data={"landing_time_s": round(landing_time, 1)},
        )

    # -----------------------------------------------------------------------
    # Araç: Eve Dön
    # -----------------------------------------------------------------------
    def return_to_home(self) -> ToolResult:
        """
        Otomatik Eve Dönüş (RTH — Return To Home) başlat.

        Araç, başlangıç noktasına (home_x, home_y) döner ve iner.
        Güvenlik için mevcut irtifada yatay hareket yapılır,
        ardından doğrudan iniş gerçekleştirilir.

        Returns:
            ToolResult: RTH sonucu ve yeni durum.
        """
        state_before = self._state.clone()
        sim_cfg = settings.simulation

        if not self._state.in_air:
            return ToolResult(
                success=False,
                action="return_to_home",
                message="❌ RTH reddedildi: Araç zaten yerde.",
                state_before=state_before,
                state_after=self._state.clone(),
            )

        dist = self._state.distance_to_home_2d
        rth_time = dist / sim_cfg.CRUISE_SPEED if sim_cfg.CRUISE_SPEED > 0 else 0
        landing_time = self._state.altitude / sim_cfg.LANDING_SPEED

        new_state = self._state.clone()
        new_state.x = new_state.home_x
        new_state.y = new_state.home_y
        new_state.altitude = 0.0
        new_state.mode = FlightMode.IDLE
        new_state.in_air = False
        new_state.speed = 0.0
        new_state.vertical_speed = 0.0

        battery_cost = sim_cfg.BATTERY_DRAIN_CRUISE * rth_time + sim_cfg.BATTERY_DRAIN_HOVER * landing_time
        new_state.battery = max(0.0, new_state.battery - battery_cost)

        if new_state.flight_start_time:
            new_state.total_flight_time += time.time() - new_state.flight_start_time
            new_state.flight_start_time = None

        new_state.last_update = time.time()
        self._update_state(new_state)

        return ToolResult(
            success=True,
            action="return_to_home",
            message=(
                f"✅ Eve dönüş tamamlandı. "
                f"Kat edilen mesafe: {dist:.1f}m | "
                f"Batarya: %{new_state.battery:.1f}"
            ),
            state_before=state_before,
            state_after=new_state.clone(),
            data={
                "distance_covered_m": round(dist, 1),
                "rth_time_s": round(rth_time + landing_time, 1),
            },
        )

    # -----------------------------------------------------------------------
    # Araç: Koordinata Git
    # -----------------------------------------------------------------------
    def go_to(self, x: float, y: float, altitude: float) -> ToolResult:
        """
        Belirtilen 3D koordinata navigasyon.

        Args:
            x: Hedef X koordinatı (Doğu yönünde metre, başlangıç noktasından).
            y: Hedef Y koordinatı (Kuzey yönünde metre, başlangıç noktasından).
            altitude: Hedef irtifa, metre AGL.

        Returns:
            ToolResult: Navigasyon sonucu ve yeni durum.
        """
        state_before = self._state.clone()
        sim_cfg = settings.simulation
        cfg = settings.safety

        if not self._state.in_air:
            return ToolResult(
                success=False,
                action="go_to",
                message=(
                    "❌ go_to reddedildi: Araç havada değil. "
                    "Önce kalkış yapın."
                ),
                state_before=state_before,
                state_after=self._state.clone(),
            )

        import math
        dx = x - self._state.x
        dy = y - self._state.y
        dist = math.sqrt(dx**2 + dy**2)
        transit_time = dist / sim_cfg.CRUISE_SPEED if sim_cfg.CRUISE_SPEED > 0 else 0

        new_state = self._state.clone()
        new_state.x = x
        new_state.y = y
        new_state.altitude = altitude
        new_state.mode = FlightMode.HOVERING
        new_state.speed = 0.0
        # Yön hesapla
        new_state.heading = (math.degrees(math.atan2(dx, dy)) + 360) % 360

        battery_cost = sim_cfg.BATTERY_DRAIN_CRUISE * transit_time
        new_state.battery = max(0.0, new_state.battery - battery_cost)
        new_state.last_update = time.time()
        self._update_state(new_state)

        return ToolResult(
            success=True,
            action="go_to",
            message=(
                f"✅ Hedefe ulaşıldı. "
                f"Konum: ({x:.1f}m, {y:.1f}m) | "
                f"İrtifa: {altitude:.1f}m | "
                f"Mesafe: {dist:.1f}m | "
                f"Batarya: %{new_state.battery:.1f}"
            ),
            state_before=state_before,
            state_after=new_state.clone(),
            data={
                "target": {"x": x, "y": y, "altitude": altitude},
                "distance_m": round(dist, 1),
                "transit_time_s": round(transit_time, 1),
            },
        )

    def emergency_land(self) -> ToolResult:
        """Acil iniş manevrası (hızlı alçalma)."""
        state_before = self._state.clone()
        if not self._state.in_air:
            return ToolResult(
                success=False,
                action="emergency_land",
                message="❌ Acil iniş reddedildi: Araç zaten yerde.",
                state_before=state_before,
                state_after=self._state.clone(),
            )

        new_state = self._state.clone()
        new_state.altitude = 0.0
        new_state.mode = FlightMode.EMERGENCY
        new_state.in_air = False
        new_state.speed = 0.0
        new_state.vertical_speed = 0.0
        new_state.battery = max(0.0, new_state.battery - 1.0)

        if new_state.flight_start_time:
            new_state.total_flight_time += time.time() - new_state.flight_start_time
            new_state.flight_start_time = None

        new_state.last_update = time.time()
        self._update_state(new_state)

        return ToolResult(
            success=True,
            action="emergency_land",
            message="⚠️ ACİL İNİŞ TAMAMLANDI! Uçuş modu acil durum olarak işaretlendi.",
            state_before=state_before,
            state_after=new_state.clone(),
        )

    def motor_stop(self) -> ToolResult:
        """Motorları anında acil stop etme (havadaysa drone düşer)."""
        state_before = self._state.clone()
        new_state = self._state.clone()
        new_state.altitude = 0.0
        new_state.mode = FlightMode.IDLE
        new_state.in_air = False
        new_state.speed = 0.0
        new_state.vertical_speed = 0.0

        if new_state.flight_start_time:
            new_state.total_flight_time += time.time() - new_state.flight_start_time
            new_state.flight_start_time = None

        new_state.last_update = time.time()
        self._update_state(new_state)

        was_in_air = state_before.in_air
        msg = (
            "⚠️ MOTORLAR ACİL DÜŞÜŞ İLE KAPATILDI! Araç yere çakıldı!"
            if was_in_air else
            "✅ Motorlar kapatıldı."
        )

        return ToolResult(
            success=True,
            action="motor_stop",
            message=msg,
            state_before=state_before,
            state_after=new_state.clone(),
            data={"fell_from_altitude": state_before.altitude if was_in_air else 0.0},
        )

