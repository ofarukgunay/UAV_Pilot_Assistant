"""
IHA Pilot Asistanı — Drone Durum Makinesi
==========================================

Bu modül, simüle edilen İHA'nın (İnsansız Hava Aracı) tüm fiziksel
ve operasyonel durumunu temsil eden veri yapılarını tanımlar.

Koordinat Sistemi (NED — North-East-Down):
    x       : Doğu yönünde metre (başlangıç noktasından)
    y       : Kuzey yönünde metre (başlangıç noktasından)
    altitude: Yer Üstü Yüksekliği, metre (AGL — Above Ground Level)

Uçuş Modları (STANAG 4586 / MAVLink HEARTBEAT.custom_mode ilham):
    IDLE           : Yerde, motorsuz bekleme
    ARMED          : Yerde, kalkışa hazır (motorlar devrede)
    TAKEOFF        : Kalkış manevrası aktif
    HOVERING       : Sabit irtifada bekleme (waypoint'e ulaşıldı)
    NAVIGATING     : Hedefe aktif yönelme
    LANDING        : İniş manevrası aktif
    RETURN_TO_HOME : Otomatik eve dönüş aktif
    EMERGENCY      : Acil durum — öncelikli iniş

Gerçek sistemde karşılığı:
    MAVLink: HEARTBEAT mesajı, custom_mode alanı (PX4 FlightMode enum)
    DJI SDK: FlightController.FlightMode
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Uçuş Modu Enum
# ---------------------------------------------------------------------------
class FlightMode(Enum):
    """
    İHA operasyonel uçuş modları.

    Her mod geçişi güvenlik katmanında doğrulanır.
    İzin verilen geçiş matrisi::

        IDLE       → ARMED, EMERGENCY
        ARMED      → TAKEOFF, IDLE, EMERGENCY
        TAKEOFF    → HOVERING, EMERGENCY
        HOVERING   → NAVIGATING, LANDING, RETURN_TO_HOME, EMERGENCY
        NAVIGATING → HOVERING, LANDING, RETURN_TO_HOME, EMERGENCY
        LANDING    → IDLE, EMERGENCY
        RETURN_TO_HOME → HOVERING, LANDING, EMERGENCY
        EMERGENCY  → IDLE  (yalnızca güvenli inişten sonra)
    """
    IDLE = "IDLE"
    ARMED = "ARMED"
    TAKEOFF = "TAKEOFF"
    HOVERING = "HOVERING"
    NAVIGATING = "NAVIGATING"
    LANDING = "LANDING"
    RETURN_TO_HOME = "RETURN_TO_HOME"
    EMERGENCY = "EMERGENCY"

    @property
    def is_airborne(self) -> bool:
        """Araç havada mı? (Yerdeki modlar: IDLE, ARMED)"""
        return self not in (FlightMode.IDLE, FlightMode.ARMED)

    @property
    def is_maneuvering(self) -> bool:
        """Araç aktif manevra yapıyor mu?"""
        return self in (
            FlightMode.TAKEOFF,
            FlightMode.NAVIGATING,
            FlightMode.LANDING,
            FlightMode.RETURN_TO_HOME,
        )

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# Drone Durum Veri Sınıfı
# ---------------------------------------------------------------------------
@dataclass
class DroneState:
    """
    İHA'nın anlık fiziksel ve operasyonel durumunu temsil eden veri sınıfı.

    Bu sınıf immutable olmayıp simülasyon döngüsü tarafından güncellenir.
    Gerçek bir sistemde telemetri stream'inden (MAVLink, DJI SDK) beslenir.

    Attributes:
        x (float): Doğu yönünde konum, metre. Başlangıç noktası (0,0).
        y (float): Kuzey yönünde konum, metre.
        altitude (float): Yer Üstü Yüksekliği (AGL), metre.
        speed (float): Anlık yatay hız, m/s.
        heading (float): Yön açısı, derece. 0=Kuzey, 90=Doğu (saat yönünde).
        vertical_speed (float): Dikey hız, m/s. Pozitif = yukarı.
        mode (FlightMode): Mevcut operasyonel mod.
        battery (float): Batarya seviyesi, yüzde (0.0–100.0).
        in_air (bool): Araç havada mı?
        home_x (float): Eve dönüş X koordinatı, metre.
        home_y (float): Eve dönüş Y koordinatı, metre.
        mission_active (bool): Aktif görev zinciri var mı?
        mission_step (int): Görev zincirindeki mevcut adım indeksi.
        last_update (float): Son durum güncelleme Unix zaman damgası.
        flight_start_time (Optional[float]): Mevcut uçuşun başlangıç zamanı.
        total_flight_time (float): Toplam uçuş süresi, saniye.
    """

    # --- Pozisyon ---
    x: float = 0.0
    y: float = 0.0
    altitude: float = 0.0

    # --- Kinematik ---
    speed: float = 0.0
    heading: float = 0.0           # derece, 0=Kuzey
    vertical_speed: float = 0.0   # m/s, + = yukarı

    # --- Sistem Durumu ---
    mode: FlightMode = FlightMode.IDLE
    battery: float = 100.0         # %
    in_air: bool = False

    # --- Referans Noktası ---
    home_x: float = 0.0
    home_y: float = 0.0
    home_altitude: float = 0.0

    # --- Görev Takibi ---
    mission_active: bool = False
    mission_step: int = 0
    mission_name: str = ""

    # --- Zaman Bilgisi ---
    last_update: float = field(default_factory=time.time)
    flight_start_time: Optional[float] = None
    total_flight_time: float = 0.0          # saniye

    # -----------------------------------------------------------------------
    # Hesaplanan Özellikler
    # -----------------------------------------------------------------------

    @property
    def distance_to_home(self) -> float:
        """
        Başlangıç noktasına olan 3 boyutlu mesafe.

        Dönüş:
            float: Metre cinsinden Öklid mesafesi.

        Not:
            3D mesafe hesabı: sqrt(dx² + dy² + dz²)
            İrtifa farkı da dahil edilir (güvenlik açısından kritik).
        """
        import math
        dx = self.x - self.home_x
        dy = self.y - self.home_y
        dz = self.altitude - self.home_altitude
        return math.sqrt(dx**2 + dy**2 + dz**2)

    @property
    def distance_to_home_2d(self) -> float:
        """Başlangıç noktasına yatay (2D) mesafe, metre."""
        import math
        dx = self.x - self.home_x
        dy = self.y - self.home_y
        return math.sqrt(dx**2 + dy**2)

    @property
    def battery_level_label(self) -> str:
        """Batarya seviyesini okunabilir etiket olarak döndür."""
        if self.battery >= 50:
            return "YETERLİ"
        elif self.battery >= 30:
            return "DÜŞÜK"
        elif self.battery >= 20:
            return "KRİTİK"
        else:
            return "ACİL"

    @property
    def flight_duration(self) -> float:
        """
        Mevcut uçuşun süresi saniye cinsinden.

        Dönüş:
            float: Saniye. Araç yerdeyse 0.0 döner.
        """
        if self.flight_start_time is None or not self.in_air:
            return 0.0
        return time.time() - self.flight_start_time

    def to_dict(self) -> dict:
        """
        Durumu JSON-serileştirilebilir sözlük olarak döndür.

        Loglama, web API yanıtları ve LLM bağlamı için kullanılır.
        """
        return {
            "position": {
                "x": round(self.x, 2),
                "y": round(self.y, 2),
                "altitude": round(self.altitude, 2),
            },
            "kinematics": {
                "speed": round(self.speed, 2),
                "heading": round(self.heading, 1),
                "vertical_speed": round(self.vertical_speed, 2),
            },
            "status": {
                "mode": self.mode.value,
                "battery": round(self.battery, 1),
                "battery_label": self.battery_level_label,
                "in_air": self.in_air,
            },
            "mission": {
                "active": self.mission_active,
                "step": self.mission_step,
                "name": self.mission_name,
            },
            "home": {
                "x": self.home_x,
                "y": self.home_y,
                "distance_2d": round(self.distance_to_home_2d, 2),
            },
            "timing": {
                "flight_duration": round(self.flight_duration, 1),
                "total_flight_time": round(self.total_flight_time, 1),
                "last_update": self.last_update,
            },
        }

    def clone(self) -> "DroneState":
        """
        Durumun derin kopyasını döndür.

        Simülasyon geçmişi kaydı ve geri alma (rollback) için kullanılır.
        """
        import copy
        return copy.deepcopy(self)

    def __repr__(self) -> str:
        return (
            f"DroneState("
            f"pos=({self.x:.1f}, {self.y:.1f}, alt={self.altitude:.1f}m), "
            f"mode={self.mode.value}, "
            f"battery={self.battery:.1f}%, "
            f"in_air={self.in_air})"
        )
