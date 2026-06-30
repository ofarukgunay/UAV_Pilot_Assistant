"""
IHA Pilot Asistanı — Simülasyon Fizik Motoru
=============================================

Bu modül, drone'un simüle edilmiş hareket fiziğini yönetir.
Gerçek bir uçuş kontrol bilgisayarının (FCC) iç döngüsünü
basitleştirilmiş biçimde modeller.

Fizik Modeli Notları:
    Bu simülasyon, gerçekçilik ve hesaplama verimliliği arasında
    denge kuran basitleştirilmiş bir nokta-kütlesi (point-mass) modelidir.
    Gerçek rotor aerodinamiği, rüzgar etkileri ve motor dinamiği
    ihmal edilmiştir.

    Referans Çalışmalar:
        - Mahony, R., et al. (2012). Multirotor Aerial Vehicles.
          IEEE Robotics & Automation Magazine.
        - DJI M300 RTK Kullanım Kılavuzu v1.5 (parametre referansı)

Fizik Sabitleri:
    g  = 9.81 m/s²  (yerçekimi ivmesi, deniz seviyesi)
    ρ  = 1.225 kg/m³ (hava yoğunluğu, ISA deniz seviyesi)
"""

from __future__ import annotations

import math
import time
from typing import Tuple

from src.simulation.drone import DroneState, FlightMode
from config.settings import settings

# Fizik sabitleri
G = 9.81       # m/s² — yerçekimi ivmesi
RHO = 1.225    # kg/m³ — standart atmosfer hava yoğunluğu (ISA, SL)


class PhysicsEngine:
    """
    Basitleştirilmiş nokta-kütlesi fizik motoru.

    Bu sınıf, simülasyon döngüsünde (tick) drone durumunu günceller.
    Her `tick()` çağrısı bir simülasyon adımını temsil eder.

    Attributes:
        tick_interval (float): Fizik güncellemesi aralığı, saniye.
                               Gerçek süreye senkronize edilir.
    """

    def __init__(self) -> None:
        cfg = settings.simulation
        self.tick_interval: float = 1.0 / cfg.PHYSICS_TICK_HZ
        self._last_tick_time: float = time.time()

    # -----------------------------------------------------------------------
    # Kalkış Simülasyonu
    # -----------------------------------------------------------------------
    def simulate_takeoff(
        self, state: DroneState, target_altitude: float, dt: float
    ) -> DroneState:
        """
        Kalkış manevrası fizik güncellemesi.

        İHA, TAKEOFF modunda hedef irtifaya TAKEOFF_SPEED hızıyla yükselir.
        Hedefe ulaşıldığında mod otomatik olarak HOVERING'e geçer.

        Args:
            state: Mevcut drone durumu.
            target_altitude: Hedef irtifa, metre AGL.
            dt: Geçen süre adımı, saniye.

        Returns:
            DroneState: Güncellenmiş drone durumu.
        """
        climb_speed = settings.simulation.TAKEOFF_SPEED
        new_alt = state.altitude + climb_speed * dt

        if new_alt >= target_altitude:
            state.altitude = target_altitude
            state.vertical_speed = 0.0
            state.mode = FlightMode.HOVERING
            state.in_air = True
        else:
            state.altitude = new_alt
            state.vertical_speed = climb_speed
            state.in_air = True

        state.battery = self._drain_battery(
            state.battery, settings.simulation.BATTERY_DRAIN_TAKEOFF, dt
        )
        state.last_update = time.time()
        return state

    # -----------------------------------------------------------------------
    # İniş Simülasyonu
    # -----------------------------------------------------------------------
    def simulate_landing(self, state: DroneState, dt: float) -> DroneState:
        """
        İniş manevrası fizik güncellemesi.

        İHA, LANDING modunda zemine LANDING_SPEED hızıyla alçalır.
        Zemine ulaşıldığında (altitude ≤ 0) mod IDLE'a geçer.

        Args:
            state: Mevcut drone durumu.
            dt: Geçen süre adımı, saniye.

        Returns:
            DroneState: Güncellenmiş drone durumu.
        """
        descent_speed = settings.simulation.LANDING_SPEED
        new_alt = state.altitude - descent_speed * dt

        if new_alt <= 0.0:
            state.altitude = 0.0
            state.vertical_speed = 0.0
            state.speed = 0.0
            state.mode = FlightMode.IDLE
            state.in_air = False
            # Uçuş süresini kaydet
            if state.flight_start_time:
                state.total_flight_time += time.time() - state.flight_start_time
                state.flight_start_time = None
        else:
            state.altitude = new_alt
            state.vertical_speed = -descent_speed

        state.battery = self._drain_battery(
            state.battery, settings.simulation.BATTERY_DRAIN_HOVER, dt
        )
        state.last_update = time.time()
        return state

    # -----------------------------------------------------------------------
    # Nokta-Nokta Navigasyon Simülasyonu
    # -----------------------------------------------------------------------
    def simulate_navigation(
        self,
        state: DroneState,
        target_x: float,
        target_y: float,
        target_alt: float,
        dt: float,
    ) -> Tuple[DroneState, bool]:
        """
        Hedefe doğru navigasyon fizik adımı.

        İHA, hedef noktaya doğru doğrusal hareket eder. Basit P-kontrol
        benzeri yaklaşımla hız profili yumuşatılır.

        Args:
            state: Mevcut drone durumu.
            target_x: Hedef X koordinatı, metre.
            target_y: Hedef Y koordinatı, metre.
            target_alt: Hedef irtifa, metre.
            dt: Zaman adımı, saniye.

        Returns:
            Tuple[DroneState, bool]: (güncellenmiş durum, hedefe ulaşıldı mı).
        """
        cruise = settings.simulation.CRUISE_SPEED

        dx = target_x - state.x
        dy = target_y - state.y
        dz = target_alt - state.altitude
        horiz_dist = math.sqrt(dx**2 + dy**2)
        total_dist = math.sqrt(horiz_dist**2 + dz**2)

        ARRIVAL_THRESHOLD = 0.5  # metre

        if total_dist < ARRIVAL_THRESHOLD:
            state.x = target_x
            state.y = target_y
            state.altitude = target_alt
            state.speed = 0.0
            state.vertical_speed = 0.0
            state.mode = FlightMode.HOVERING
            state.battery = self._drain_battery(
                state.battery, settings.simulation.BATTERY_DRAIN_HOVER, dt
            )
            state.last_update = time.time()
            return state, True

        # Yön açısını hesapla (Kuzey = 0°, saat yönünde)
        state.heading = (math.degrees(math.atan2(dx, dy)) + 360) % 360

        # Hız bileşenlerini hesapla
        move_dist = min(cruise * dt, total_dist)
        ratio = move_dist / total_dist

        state.x += dx * ratio
        state.y += dy * ratio
        state.altitude += dz * ratio
        state.speed = cruise
        state.vertical_speed = dz * ratio / dt if dt > 0 else 0.0
        state.mode = FlightMode.NAVIGATING
        state.in_air = True

        state.battery = self._drain_battery(
            state.battery, settings.simulation.BATTERY_DRAIN_CRUISE, dt
        )
        state.last_update = time.time()
        return state, False

    # -----------------------------------------------------------------------
    # Hovering Simülasyonu (Sabit İrtifada Bekleme)
    # -----------------------------------------------------------------------
    def simulate_hover(self, state: DroneState, dt: float) -> DroneState:
        """
        Sabit konumda bekleme (hovering) batarya tüketimi.

        Args:
            state: Mevcut drone durumu.
            dt: Zaman adımı, saniye.

        Returns:
            DroneState: Güncellenmiş drone durumu.
        """
        state.speed = 0.0
        state.vertical_speed = 0.0
        state.battery = self._drain_battery(
            state.battery, settings.simulation.BATTERY_DRAIN_HOVER, dt
        )
        state.last_update = time.time()
        return state

    # -----------------------------------------------------------------------
    # Yardımcı: Batarya Tüketimi
    # -----------------------------------------------------------------------
    @staticmethod
    def _drain_battery(current: float, rate: float, dt: float) -> float:
        """
        Batarya seviyesini güncelle.

        Args:
            current: Mevcut batarya yüzdesi (0–100).
            rate: Tüketim oranı, %/saniye.
            dt: Zaman adımı, saniye.

        Returns:
            float: Güncellenmiş batarya seviyesi (0.0 altına düşmez).
        """
        return max(0.0, current - rate * dt)
